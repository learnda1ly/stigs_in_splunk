"""RMF package labels, host defaults, host×baseline overrides, and denormalized review ids."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple

import access
import audit
import kv_client
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_HOSTS,
    KV_STIG_HOST_BASELINE_RMF_OVERRIDES,
    KV_STIG_HOST_RMF_DEFAULTS,
    KV_STIG_REVIEWS,
    KV_STIG_RMF_PACKAGES,
    RMF_SYSTEM_PACKAGE_ID,
    RMF_SYSTEM_PACKAGE_NAME,
    kv_record,
    now_epoch,
)
from services import baselines as baselines_svc


def normalize_hostname_key(hostname: str) -> str:
    return (hostname or "").strip().casefold()


def normalize_baseline_ref(value: str) -> str:
    return (value or "").strip()


def _require_rmf_admin(session: Dict[str, Any]) -> None:
    if not access.user_has_stig_admin(session):
        raise PermissionError("stig_admin required")


def _packages_coll(service):
    return kv_client.get_collection(service, KV_STIG_RMF_PACKAGES)


def _defaults_coll(service):
    return kv_client.get_collection(service, KV_STIG_HOST_RMF_DEFAULTS)


def _overrides_coll(service):
    return kv_client.get_collection(service, KV_STIG_HOST_BASELINE_RMF_OVERRIDES)


def _override_key(hostname_key: str, baseline_ref: str) -> str:
    raw = f"{hostname_key}|{normalize_baseline_ref(baseline_ref).casefold()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_system_package(service, username: str = "system") -> Dict[str, Any]:
    coll = _packages_coll(service)
    existing = kv_client.get_by_key(coll, RMF_SYSTEM_PACKAGE_ID)
    if existing:
        return existing
    ts = now_epoch()
    record = kv_record(
        {
            "_key": RMF_SYSTEM_PACKAGE_ID,
            "name": RMF_SYSTEM_PACKAGE_NAME,
            "is_system": True,
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    return kv_client.insert_record(coll, record)


def package_ids(service) -> Set[str]:
    ensure_system_package(service)
    coll = _packages_coll(service)
    return {str(rec["_key"]) for rec in kv_client.query_all(coll) if rec.get("_key")}


def validate_package_id(service, package_id: str) -> str:
    pid = str(package_id or "").strip()
    if not pid:
        raise ValueError("package_id is required")
    ensure_system_package(service)
    if pid not in package_ids(service):
        raise ValueError(f"unknown RMF package_id: {pid}")
    return pid


def list_packages(service, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not access.user_has_stig_write(session) and not access.user_has_stig_admin(session):
        raise PermissionError("stig_read required")
    ensure_system_package(service)
    coll = _packages_coll(service)
    rows = kv_client.query_all(coll)
    rows.sort(key=lambda rec: (not rec.get("is_system"), rec.get("_key") or ""))
    return rows


def get_package(service, package_id: str, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not access.user_has_stig_write(session) and not access.user_has_stig_admin(session):
        raise PermissionError("stig_read required")
    ensure_system_package(service)
    coll = _packages_coll(service)
    return kv_client.get_by_key(coll, package_id)


def create_package(
    service, body: Dict[str, Any], username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    _require_rmf_admin(session)
    ensure_system_package(service, username)
    package_id = str(body.get("id") or body.get("package_id") or "").strip()
    name = (body.get("name") or "").strip()
    if not package_id:
        raise ValueError("id is required")
    if package_id == RMF_SYSTEM_PACKAGE_ID:
        raise ValueError("reserved package id")
    if not name:
        raise ValueError("name is required")
    coll = _packages_coll(service)
    if kv_client.get_by_key(coll, package_id):
        raise ValueError(f"package id already exists: {package_id}")
    ts = now_epoch()
    record = kv_record(
        {
            "_key": package_id,
            "name": name,
            "is_system": False,
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored = kv_client.insert_record(coll, record)
    audit.log_event("create", "stig_rmf_package", package_id, username, {"name": name})
    return stored


def update_package(
    service,
    package_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_rmf_admin(session)
    ensure_system_package(service, username)
    coll = _packages_coll(service)
    existing = kv_client.get_by_key(coll, package_id)
    if not existing:
        raise KeyError(package_id)
    if existing.get("is_system") and body.get("id") not in (None, "", package_id):
        if str(body.get("id") or "").strip() != RMF_SYSTEM_PACKAGE_ID:
            raise ValueError("system package id cannot be renamed")

    new_id = str(body.get("id") or body.get("new_id") or "").strip()
    if new_id and new_id != package_id:
        if existing.get("is_system"):
            raise ValueError("system package id cannot be renamed")
        if kv_client.get_by_key(coll, new_id):
            raise ValueError(f"package id already exists: {new_id}")
        _bulk_rewrite_package_id(service, package_id, new_id, username)
        existing = kv_client.get_by_key(coll, new_id) or existing
        package_id = new_id

    patch = dict(existing)
    if "name" in body:
        patch["name"] = (body.get("name") or "").strip()
        if not patch["name"]:
            raise ValueError("name is required")
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, package_id, kv_record(patch))
    audit.log_event("update", "stig_rmf_package", package_id, username, body)
    return stored


def delete_package(
    service, package_id: str, username: str, session: Dict[str, Any]
) -> None:
    _require_rmf_admin(session)
    ensure_system_package(service, username)
    if package_id == RMF_SYSTEM_PACKAGE_ID:
        raise ValueError("system package cannot be deleted")
    coll = _packages_coll(service)
    existing = kv_client.get_by_key(coll, package_id)
    if not existing:
        raise KeyError(package_id)
    if existing.get("is_system"):
        raise ValueError("system package cannot be deleted")
    kv_client.delete_record(coll, package_id)
    audit.log_event("delete", "stig_rmf_package", package_id, username)


def _bulk_rewrite_package_id(
    service, old_id: str, new_id: str, username: str
) -> Dict[str, int]:
    counts = {"defaults": 0, "overrides": 0, "reviews": 0}
    defaults = _defaults_coll(service)
    for rec in kv_client.query_all(defaults, {"package_id": old_id}):
        patch = dict(rec)
        patch["package_id"] = new_id
        patch["updated_at"] = now_epoch()
        patch["updated_by"] = username
        kv_client.update_record(defaults, rec["_key"], kv_record(patch))
        counts["defaults"] += 1

    overrides = _overrides_coll(service)
    for rec in kv_client.query_all(overrides, {"package_id": old_id}):
        patch = dict(rec)
        patch["package_id"] = new_id
        patch["updated_at"] = now_epoch()
        patch["updated_by"] = username
        kv_client.update_record(overrides, rec["_key"], kv_record(patch))
        counts["overrides"] += 1

    reviews = kv_client.get_collection(service, KV_STIG_REVIEWS)
    for rec in kv_client.query_all(reviews, {"rmf_package_id": old_id}):
        patch = dict(rec)
        patch["rmf_package_id"] = new_id
        patch["updated_at"] = now_epoch()
        patch["updated_by"] = username
        kv_client.update_record(reviews, rec["_key"], kv_record(patch))
        counts["reviews"] += 1

    pkg_coll = _packages_coll(service)
    old_rec = kv_client.get_by_key(pkg_coll, old_id)
    if old_rec:
        new_rec = dict(old_rec)
        new_rec["_key"] = new_id
        new_rec["updated_at"] = now_epoch()
        new_rec["updated_by"] = username
        kv_client.insert_record(pkg_coll, kv_record(new_rec))
        kv_client.delete_record(pkg_coll, old_id)
    return counts


def list_host_defaults(service, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not access.user_has_stig_write(session) and not access.user_has_stig_admin(session):
        raise PermissionError("stig_read required")
    ensure_system_package(service)
    return kv_client.query_all(_defaults_coll(service))


def list_baseline_overrides(service, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not access.user_has_stig_write(session) and not access.user_has_stig_admin(session):
        raise PermissionError("stig_read required")
    ensure_system_package(service)
    return kv_client.query_all(_overrides_coll(service))


def _get_host_default(service, hostname_key: str) -> Optional[str]:
    coll = _defaults_coll(service)
    rec = kv_client.get_by_key(coll, hostname_key)
    if rec and rec.get("package_id"):
        return str(rec["package_id"])
    return None


def _get_baseline_override(
    service, hostname_key: str, baseline_id: str, baseline_stig_id: str
) -> Optional[str]:
    coll = _overrides_coll(service)
    refs = {normalize_baseline_ref(baseline_id).casefold()}
    if baseline_stig_id:
        refs.add(normalize_baseline_ref(baseline_stig_id).casefold())
    for rec in kv_client.query_all(coll, {"hostname": hostname_key}):
        ref = normalize_baseline_ref(rec.get("baseline_ref") or "").casefold()
        if ref in refs and rec.get("package_id"):
            return str(rec["package_id"])
    return None


def resolve_package_id(
    service,
    hostname: str,
    baseline_id: str = "",
    baseline_stig_id: str = "",
) -> str:
    """Resolution order: host×baseline override, host default, system unassigned (-1)."""
    ensure_system_package(service)
    hostname_key = normalize_hostname_key(hostname)
    if not hostname_key:
        return RMF_SYSTEM_PACKAGE_ID
    override = _get_baseline_override(
        service, hostname_key, baseline_id, baseline_stig_id
    )
    if override:
        return override
    default = _get_host_default(service, hostname_key)
    if default:
        return default
    return RMF_SYSTEM_PACKAGE_ID


def set_host_default(
    service,
    hostname: str,
    package_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_rmf_admin(session)
    hostname_key = normalize_hostname_key(hostname)
    if not hostname_key:
        raise ValueError("host is required")
    pid = validate_package_id(service, package_id)
    coll = _defaults_coll(service)
    ts = now_epoch()
    existing = kv_client.get_by_key(coll, hostname_key)
    record = kv_record(
        {
            "_key": hostname_key,
            "hostname": hostname_key,
            "package_id": pid,
            "updated_at": ts,
            "updated_by": username,
        }
    )
    if existing:
        record["created_at"] = existing.get("created_at") or ts
        record["created_by"] = existing.get("created_by") or username
        stored = kv_client.update_record(coll, hostname_key, record)
    else:
        record["created_at"] = ts
        record["created_by"] = username
        stored = kv_client.insert_record(coll, record)
    sync_denormalized_for_hostname(service, hostname_key, username=username)
    audit.log_event(
        "default.set",
        "stig_host_rmf_default",
        hostname_key,
        username,
        {"package_id": pid},
    )
    return stored


def set_baseline_override(
    service,
    hostname: str,
    baseline_ref: str,
    package_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_rmf_admin(session)
    hostname_key = normalize_hostname_key(hostname)
    baseline_ref_norm = normalize_baseline_ref(baseline_ref)
    if not hostname_key or not baseline_ref_norm:
        raise ValueError("host and baseline are required")
    pid = validate_package_id(service, package_id)
    key = _override_key(hostname_key, baseline_ref_norm)
    coll = _overrides_coll(service)
    ts = now_epoch()
    existing = kv_client.get_by_key(coll, key)
    record = kv_record(
        {
            "_key": key,
            "hostname": hostname_key,
            "baseline_ref": baseline_ref_norm,
            "package_id": pid,
            "updated_at": ts,
            "updated_by": username,
        }
    )
    if existing:
        record["created_at"] = existing.get("created_at") or ts
        record["created_by"] = existing.get("created_by") or username
        stored = kv_client.update_record(coll, key, record)
    else:
        record["created_at"] = ts
        record["created_by"] = username
        stored = kv_client.insert_record(coll, record)
    sync_denormalized_for_hostname(
        service,
        hostname_key,
        username=username,
        baseline_ref_filter=baseline_ref_norm,
    )
    audit.log_event(
        "override.set",
        "stig_host_baseline_rmf_override",
        key,
        username,
        {"hostname": hostname_key, "baseline_ref": baseline_ref_norm, "package_id": pid},
    )
    return stored


def delete_baseline_override(
    service, key: str, username: str, session: Dict[str, Any]
) -> None:
    _require_rmf_admin(session)
    coll = _overrides_coll(service)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    kv_client.delete_record(coll, key)
    sync_denormalized_for_hostname(
        service,
        existing.get("hostname") or "",
        username=username,
        baseline_ref_filter=existing.get("baseline_ref") or "",
    )
    audit.log_event("override.delete", "stig_host_baseline_rmf_override", key, username)


def ingest_assignment_rows(
    service,
    rows: List[Dict[str, Any]],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_rmf_admin(session)
    ensure_system_package(service, username)
    applied = 0
    errors: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows or []):
        host = row.get("host") or row.get("hostname") or ""
        baseline = row.get("baseline") or row.get("baseline_ref") or row.get("baseline_id")
        package_id = row.get("package_id") or ""
        try:
            if baseline is None or str(baseline).strip() == "":
                set_host_default(service, host, package_id, username, session)
            else:
                set_baseline_override(
                    service, host, str(baseline), package_id, username, session
                )
            applied += 1
        except (ValueError, PermissionError) as exc:
            errors.append({"index": idx, "error": str(exc), "row": row})
    return {"applied": applied, "errors": errors}


def bulk_assign_combos(
    service,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_rmf_admin(session)
    assignments = body.get("assignments") or body.get("combos") or []
    if not isinstance(assignments, list):
        raise ValueError("assignments must be a list")
    rows = []
    for item in assignments:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "host": item.get("hostname") or item.get("host"),
                "baseline": item.get("baseline_ref")
                or item.get("baseline_id")
                or item.get("baseline"),
                "package_id": item.get("package_id"),
            }
        )
    return ingest_assignment_rows(service, rows, username, session)


def _hosts_by_hostname_key(service, hostname_key: str) -> List[Dict[str, Any]]:
    if not hostname_key:
        return []
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    return [
        rec
        for rec in kv_client.query_all(coll)
        if normalize_hostname_key(rec.get("hostname") or "") == hostname_key
    ]


def _baseline_matches_ref(
    baseline_id: str, baseline_stig_id: str, baseline_ref_filter: str
) -> bool:
    if not baseline_ref_filter:
        return True
    ref = normalize_baseline_ref(baseline_ref_filter).casefold()
    return ref in {
        normalize_baseline_ref(baseline_id).casefold(),
        normalize_baseline_ref(baseline_stig_id).casefold(),
    }


def sync_denormalized_for_hostname(
    service,
    hostname_key: str,
    *,
    username: str = "system",
    baseline_ref_filter: str = "",
) -> int:
    """Rewrite rmf_package_id on reviews for one normalized hostname (optional baseline filter)."""
    hostname_key = normalize_hostname_key(hostname_key)
    if not hostname_key:
        return 0
    updated = 0
    checklists_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    for host in _hosts_by_hostname_key(service, hostname_key):
        host_name = host.get("hostname") or hostname_key
        for checklist in kv_client.query_all(
            checklists_coll, {"host_id": host.get("_key")}
        ):
            baseline_id = str(checklist.get("baseline_id") or "")
            baseline = baselines_svc.get_baseline(service, baseline_id) or {}
            stig_id = str(baseline.get("stig_id") or "")
            if not _baseline_matches_ref(baseline_id, stig_id, baseline_ref_filter):
                continue
            resolved = resolve_package_id(service, host_name, baseline_id, stig_id)
            for review in kv_client.query_all(
                reviews_coll, {"checklist_id": checklist.get("_key")}
            ):
                if str(review.get("rmf_package_id") or "") == resolved:
                    continue
                patch = dict(review)
                patch["rmf_package_id"] = resolved
                patch["updated_at"] = now_epoch()
                patch["updated_by"] = username
                kv_client.update_record(reviews_coll, review["_key"], kv_record(patch))
                updated += 1
    return updated


def stamp_review_rmf_package_id(
    service,
    review: Dict[str, Any],
    *,
    hostname: str,
    baseline_id: str = "",
    baseline_stig_id: str = "",
) -> str:
    resolved = resolve_package_id(service, hostname, baseline_id, baseline_stig_id)
    review["rmf_package_id"] = resolved
    return resolved


def resolve_for_checklist(
    service, host: Dict[str, Any], checklist: Dict[str, Any]
) -> Tuple[str, str, str]:
    hostname = host.get("hostname") or ""
    baseline_id = str(checklist.get("baseline_id") or "")
    baseline = baselines_svc.get_baseline(service, baseline_id) or {}
    stig_id = str(baseline.get("stig_id") or "")
    resolved = resolve_package_id(service, hostname, baseline_id, stig_id)
    return resolved, baseline_id, stig_id
