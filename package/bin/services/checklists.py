"""stig_checklists CRUD, review spawn, export."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import base64
import io
import re
import zipfile

import access
import audit
import kv_client
import review_workflow
import validation
from exporters import ckl as ckl_export
from exporters import cklb as cklb_export
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_REVIEWS,
    dumps_json,
    is_ingest_locked,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)
from importers.ingest import match_review_seed
from services import baselines as baselines_svc
from services import baseline_defaults as baseline_defaults_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import hosts as hosts_svc


def _require_collection(service, collection_id: str, session: Dict[str, Any], write: bool = False):
    try:
        if write:
            grants_svc.require_workspace_write(service, collection_id, session)
        else:
            grants_svc.require_workspace_read(service, collection_id, session)
    except KeyError as exc:
        raise KeyError(collection_id) from exc


def _access_context(service, collection_id: str, session: Dict[str, Any]):
    _rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    return ctx


def list_checklists(
    service, session: Dict[str, Any], stig_collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    query = {"stig_collection_id": stig_collection_id} if stig_collection_id else {}
    records = kv_client.query_all(coll, query)
    if stig_collection_id:
        _require_collection(service, stig_collection_id, session)
        ctx = _access_context(service, stig_collection_id, session)
        return access.filter_checklists(records, ctx)
    visible = collections_svc.list_collections(service, session)
    by_id = {r["_key"]: r for r in visible}
    out: List[Dict[str, Any]] = []
    for rec in records:
        cid = rec.get("stig_collection_id")
        if cid not in by_id:
            continue
        ctx = _access_context(service, cid, session)
        if access.checklist_allowed(rec, ctx):
            out.append(rec)
    return out


def get_checklist(
    service, key: str, session: Dict[str, Any], write: bool = False
) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    rec = kv_client.get_by_key(coll, key)
    if not rec:
        return None
    try:
        _require_collection(service, rec["stig_collection_id"], session, write=write)
    except (KeyError, PermissionError):
        return None
    ctx = _access_context(service, rec["stig_collection_id"], session)
    if not access.checklist_allowed(rec, ctx):
        return None
    return rec


def find_checklist(
    service,
    session: Dict[str, Any],
    stig_collection_id: str,
    host_id: str,
    baseline_id: str,
) -> Optional[Dict[str, Any]]:
    for rec in list_checklists(service, session, stig_collection_id):
        if rec.get("host_id") == host_id and rec.get("baseline_id") == baseline_id:
            return rec
    return None


def list_checklists_for_host(
    service, host_id: str, session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    host = hosts_svc.get_host(service, host_id, session)
    if not host:
        raise KeyError(host_id)
    collection_id = host.get("stig_collection_id") or ""
    return [
        rec
        for rec in list_checklists(service, session, collection_id)
        if rec.get("host_id") == host_id
    ]


def _resolve_checklist_baseline_id(
    service, body: Dict[str, Any], collection_id: str
) -> str:
    baseline_id = (body.get("baseline_id") or "").strip()
    stig_id = (body.get("stig_id") or body.get("benchmark_id") or "").strip()
    if not baseline_id:
        if not stig_id:
            raise ValueError(
                "baseline_id is required unless stig_id is provided for workspace default resolution"
            )
        baseline_id = baseline_defaults_svc.resolve_baseline_id(
            service,
            collection_id=collection_id,
            stig_id=stig_id,
            xccdf_benchmark_id=body.get("xccdf_benchmark_id") or "",
            version=str(body.get("version") or ""),
        )
        if not baseline_id:
            raise ValueError(f"no baseline found for stig_id {stig_id}")
    return baseline_id


def resolve_baseline_ref(
    service,
    collection_id: str,
    baseline_ref: str,
) -> str:
    """Resolve a REST path segment: KV baseline `_key` or logical `stig_id`.

    Uses the same precedence as POST assign: explicit baseline row → workspace
    `default_baseline_map` → versioned catalog match → latest revision.
    """
    ref = (baseline_ref or "").strip()
    if not ref:
        raise ValueError("baseline reference is required")
    if baselines_svc.get_baseline(service, ref):
        return ref
    return _resolve_checklist_baseline_id(
        service,
        {"stig_id": ref, "benchmark_id": ref},
        collection_id,
    )


def _find_existing_checklist_row(
    service,
    collection_id: str,
    host_id: str,
    baseline_id: str,
    session: Optional[Dict[str, Any]] = None,
    username: str = "system",
) -> Optional[Dict[str, Any]]:
    checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    rows = kv_client.query_all(
        checklist_coll,
        {
            "stig_collection_id": collection_id,
            "host_id": host_id,
            "baseline_id": baseline_id,
        },
    )
    if not rows:
        return None
    if len(rows) > 1:
        audit.log_event(
            "data_integrity",
            "stig_checklist",
            host_id,
            username,
            {
                "issue": "duplicate_host_baseline",
                "count": len(rows),
                "baseline_id": baseline_id,
                "checklist_ids": [r.get("_key") for r in rows],
            },
        )
    ordered = sorted(rows, key=lambda rec: rec.get("_key") or "")
    if session is not None:
        ctx = _access_context(service, collection_id, session)
        for rec in ordered:
            if access.checklist_allowed(rec, ctx):
                return rec
        return None
    return ordered[0]


def _spawn_checklist_with_reviews(
    service,
    *,
    collection_id: str,
    host: Dict[str, Any],
    baseline: Dict[str, Any],
    baseline_id: str,
    rules: List[Dict[str, Any]],
    body: Dict[str, Any],
    username: str,
    review_seeds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    target_data = {
        "host_name": host.get("hostname") or "",
        "ip_address": host.get("ip_address") or "",
        "fqdn": host.get("fqdn") or "",
        "mac_address": host.get("mac_address") or "",
        "role": host.get("role") or "None",
        "asset_type": host.get("asset_type") or "Computing",
    }
    if body.get("target_data"):
        target_data.update(body["target_data"])

    checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)

    ts = now_epoch()
    title = body.get("title") or baseline.get("title") or "Checklist"
    checklist_record = kv_record(
        {
            "stig_collection_id": collection_id,
            "host_id": host["_key"],
            "baseline_id": baseline_id,
            "title": title,
            "mode": int(body.get("mode") or 1),
            "target_data": dumps_json(target_data),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored_checklist = kv_client.insert_record(checklist_coll, checklist_record)
    checklist_id = stored_checklist["_key"]

    review_records = []
    for rule in rules:
        seed = match_review_seed(rule, review_seeds)
        review = {
            "checklist_id": checklist_id,
            "baseline_id": baseline_id,
            "group_id": rule.get("group_id"),
            "rule_id": rule.get("rule_id"),
            "rule_version": rule.get("rule_version"),
            "check_content_hash": rule.get("check_content_hash"),
            "status": seed.get("status") or "not_reviewed",
            "finding_details": seed.get("finding_details") or "",
            "comments": seed.get("comments") or "",
            "package_id": str(seed.get("package_id") or ""),
            "ingest_lock": False,
            "workflow_state": "draft",
            "updated_at": ts,
            "updated_by": username,
        }
        review["valid"] = validation.persistable_valid(review)
        review_records.append(kv_record(review))
    kv_client.batch_insert(reviews_coll, review_records)

    audit.log_event(
        "create",
        "stig_checklist",
        checklist_id,
        username,
        {"reviews": len(review_records), "assign": True},
    )
    return stored_checklist


def assign_stig_to_host(
    service,
    host_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
    review_seeds: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """Idempotent assign: create checklist + reviews or return existing row."""
    host = hosts_svc.get_host(service, host_id, session)
    if not host:
        raise KeyError(host_id)
    collection_id = host.get("stig_collection_id") or ""
    if not collection_id:
        raise ValueError("host has no stig_collection_id")

    baseline_id = _resolve_checklist_baseline_id(service, body, collection_id)
    _require_collection(service, collection_id, session, write=True)

    existing = _find_existing_checklist_row(
        service, collection_id, host_id, baseline_id, session=session, username=username
    )
    if existing:
        ctx = _access_context(service, collection_id, session)
        if not access.checklist_allowed(existing, ctx):
            raise PermissionError("checklist not accessible for this grant")
        audit.log_event(
            "assign",
            "stig_checklist",
            existing["_key"],
            username,
            {"idempotent": True, "baseline_id": baseline_id},
        )
        return existing, False

    baseline = baselines_svc.get_baseline(service, baseline_id)
    if not baseline:
        raise KeyError(baseline_id)

    rules = baselines_svc.list_baseline_rules(service, baseline_id)
    if not rules:
        raise ValueError("baseline has no rules")

    stored = _spawn_checklist_with_reviews(
        service,
        collection_id=collection_id,
        host=host,
        baseline=baseline,
        baseline_id=baseline_id,
        rules=rules,
        body=body,
        username=username,
        review_seeds=review_seeds,
    )
    return stored, True


def unassign_stig_from_host(
    service,
    host_id: str,
    baseline_ref: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """Remove one host×baseline assignment (checklist + reviews).

    ``baseline_ref`` is either a baseline KV ``_key`` or a logical ``stig_id``.
    Resolution matches POST assign. Only the checklist for that resolved
    ``baseline_id`` is removed; other revision checklists for the same ``stig_id``
    on the host require DELETE with each revision's explicit baseline ``_key``.
    """
    host = hosts_svc.get_host(service, host_id, session)
    if not host:
        raise KeyError(host_id)
    collection_id = host.get("stig_collection_id") or ""
    if not collection_id:
        raise ValueError("host has no stig_collection_id")

    try:
        baseline_id = resolve_baseline_ref(service, collection_id, baseline_ref)
    except ValueError as exc:
        raise KeyError(baseline_ref) from exc

    _require_collection(service, collection_id, session, write=True)
    existing = find_checklist(service, session, collection_id, host_id, baseline_id)
    if not existing:
        raise KeyError("checklist")

    delete_checklist(service, existing["_key"], username, session)
    audit.log_event(
        "unassign",
        "stig_checklist",
        existing["_key"],
        username,
        {"baseline_id": baseline_id, "baseline_ref": baseline_ref},
    )
    return {"deleted": existing["_key"], "baseline_id": baseline_id}


def apply_review_seeds(
    service,
    checklist_id: str,
    seeds: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, int]:
    get_checklist(service, checklist_id, session, write=True)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    records = kv_client.query_all(reviews_coll, {"checklist_id": checklist_id})
    updated = 0
    unmatched = 0
    locked = 0
    ts = now_epoch()
    for rec in records:
        seed = match_review_seed(rec, seeds)
        if not seed:
            unmatched += 1
            continue
        if is_ingest_locked(rec) or not review_workflow.is_ingest_mutable(rec):
            locked += 1
            continue
        patch = dict(rec)
        if "status" in seed:
            patch["status"] = seed["status"]
        if "finding_details" in seed:
            patch["finding_details"] = seed["finding_details"] or ""
        if "comments" in seed:
            patch["comments"] = seed["comments"] or ""
        if "package_id" in seed:
            patch["package_id"] = seed["package_id"] or ""
        patch["valid"] = validation.persistable_valid(patch)
        patch["updated_at"] = ts
        patch["updated_by"] = username
        kv_client.update_record(reviews_coll, rec["_key"], kv_record(patch))
        updated += 1
    return {"updated": updated, "unmatched": unmatched, "locked": locked}


def create_checklist(
    service,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
    review_seeds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    collection_id = body.get("stig_collection_id")
    host_id = body.get("host_id")
    if not collection_id or not host_id:
        raise ValueError("stig_collection_id and host_id are required")
    baseline_id = _resolve_checklist_baseline_id(service, body, collection_id)

    _require_collection(service, collection_id, session, write=True)
    host = hosts_svc.get_host(service, host_id, session)
    if not host or host.get("stig_collection_id") != collection_id:
        raise ValueError("host not found in stig_collection")
    baseline = baselines_svc.get_baseline(service, baseline_id)
    if not baseline:
        raise KeyError(baseline_id)

    rules = baselines_svc.list_baseline_rules(service, baseline_id)
    if not rules:
        raise ValueError("baseline has no rules")

    if _find_existing_checklist_row(service, collection_id, host_id, baseline_id):
        raise ValueError("a checklist already exists for this host and baseline")

    return _spawn_checklist_with_reviews(
        service,
        collection_id=collection_id,
        host=host,
        baseline=baseline,
        baseline_id=baseline_id,
        rules=rules,
        body=body,
        username=username,
        review_seeds=review_seeds,
    )


def ensure_review(
    service,
    checklist: Dict[str, Any],
    rule: Dict[str, Any],
    username: str,
    seed: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    checklist_id = checklist.get("_key") or ""
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    records = kv_client.query_all(reviews_coll, {"checklist_id": checklist_id})
    want = {
        str(rule.get("rule_id") or ""),
        str(rule.get("rule_id_src") or ""),
        str(rule.get("group_id") or ""),
    }
    want.discard("")
    for rec in records:
        keys = {str(rec.get("rule_id") or ""), str(rec.get("group_id") or "")}
        keys.discard("")
        if keys.intersection(want):
            return rec, False
    seed = seed or {}
    ts = now_epoch()
    review = {
        "checklist_id": checklist_id,
        "baseline_id": checklist.get("baseline_id"),
        "group_id": rule.get("group_id"),
        "rule_id": rule.get("rule_id"),
        "rule_version": rule.get("rule_version"),
        "check_content_hash": rule.get("check_content_hash"),
        "status": seed.get("status") or "not_reviewed",
        "finding_details": seed.get("finding_details") or "",
        "comments": seed.get("comments") or "",
        "package_id": str(seed.get("package_id") or ""),
        "ingest_lock": False,
        "workflow_state": "draft",
        "updated_at": ts,
        "updated_by": username,
    }
    review["valid"] = validation.persistable_valid(review)
    stored = kv_client.insert_record(reviews_coll, kv_record(review))
    return stored, True


def update_checklist(
    service, key: str, body: Dict[str, Any], username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection(service, existing["stig_collection_id"], session, write=True)

    patch = dict(existing)
    if "title" in body:
        patch["title"] = body["title"]
    if "mode" in body:
        patch["mode"] = int(body["mode"])
    if "target_data" in body:
        val = body["target_data"]
        patch["target_data"] = dumps_json(val) if isinstance(val, dict) else val
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_checklist", key, username, body)
    return stored


def delete_checklist(service, key: str, username: str, session: Dict[str, Any]) -> None:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection(service, existing["stig_collection_id"], session, write=True)

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    for review in kv_client.query_all(reviews_coll, {"checklist_id": key}):
        kv_client.delete_record(reviews_coll, review["_key"])
    kv_client.delete_record(coll, key)
    audit.log_event("delete", "stig_checklist", key, username)


def export_checklist(
    service, key: str, fmt: str, session: Dict[str, Any]
) -> str:
    checklist = get_checklist(service, key, session)
    if not checklist:
        raise KeyError(key)
    baseline = baselines_svc.get_baseline(service, checklist["baseline_id"])
    if not baseline:
        raise KeyError(checklist["baseline_id"])
    host = hosts_svc.get_host(service, checklist["host_id"], session)
    if not host:
        raise KeyError(checklist["host_id"])

    rules = baselines_svc.list_baseline_rules(service, checklist["baseline_id"])
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    reviews = kv_client.query_all(reviews_coll, {"checklist_id": key})
    reviews_by_group = {r.get("group_id"): r for r in reviews if r.get("group_id")}
    for rec in reviews:
        if rec.get("rule_id"):
            reviews_by_group.setdefault(rec["rule_id"], rec)
        if rec.get("rule_version"):
            reviews_by_group.setdefault(rec["rule_version"], rec)

    export_fmt = (fmt or "cklb").lower()
    if export_fmt == "ckl":
        return ckl_export.export_ckl(checklist, baseline, rules, reviews, host)
    return cklb_export.export_cklb(checklist, baseline, rules, reviews, host)


def _safe_filename_part(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return text.strip("._") or "item"


def export_filename(
    checklist: Dict[str, Any],
    baseline: Dict[str, Any],
    host: Dict[str, Any],
    fmt: str,
) -> str:
    host_part = _safe_filename_part(host.get("hostname") or checklist.get("_key"))
    stig_part = _safe_filename_part(
        baseline.get("stig_id") or baseline.get("title") or "stig"
    )
    version = _safe_filename_part(baseline.get("version") or "")
    ext = "ckl" if (fmt or "").lower() == "ckl" else "cklb"
    name = f"{host_part}_{stig_part}"
    if version:
        name += f"_{version}"
    return f"{name}.{ext}"


def export_checklist_file(
    service, key: str, fmt: str, session: Dict[str, Any]
) -> Tuple[str, str]:
    checklist = get_checklist(service, key, session)
    if not checklist:
        raise KeyError(key)
    baseline = baselines_svc.get_baseline(service, checklist["baseline_id"])
    if not baseline:
        raise KeyError(checklist["baseline_id"])
    host = hosts_svc.get_host(service, checklist["host_id"], session)
    if not host:
        raise KeyError(checklist["host_id"])
    content = export_checklist(service, key, fmt, session)
    return content, export_filename(checklist, baseline, host, fmt)


def export_checklists_bulk(
    service,
    checklist_ids: List[str],
    fmt: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    ids = [str(i).strip() for i in checklist_ids or [] if str(i).strip()]
    if not ids:
        raise ValueError("checklist_ids is required")
    export_fmt = (fmt or "cklb").lower()
    if export_fmt not in {"ckl", "cklb"}:
        raise ValueError("format must be ckl or cklb")

    buf = io.BytesIO()
    files: List[str] = []
    used: Dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for key in ids:
            content, filename = export_checklist_file(service, key, export_fmt, session)
            count = used.get(filename, 0)
            used[filename] = count + 1
            if count:
                stem, ext = filename.rsplit(".", 1)
                filename = f"{stem}_{count + 1}.{ext}"
            archive.writestr(filename, content)
            files.append(filename)

    zip_name = f"stig-checklists-{export_fmt}.zip"
    return {
        "filename": zip_name,
        "format": export_fmt,
        "count": len(files),
        "files": files,
        "content_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def _by_key(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for rec in records or []:
        key = rec.get("_key")
        if key:
            out[str(key)] = rec
    return out


def summarize_checklists(
    service, session: Dict[str, Any], stig_collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    checklists = list_checklists(service, session, stig_collection_id)
    collections = _by_key(collections_svc.list_collections(service, session))
    host_query = stig_collection_id or None
    try:
        hosts = _by_key(hosts_svc.list_hosts(service, session, host_query))
    except Exception:
        hosts = {}
    try:
        baselines = _by_key(baselines_svc.list_baselines(service))
    except Exception:
        baselines = {}

    reviews_by_checklist: Dict[str, List[Dict[str, Any]]] = {}
    try:
        reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
        for checklist in checklists:
            key = checklist.get("_key")
            if not key:
                continue
            reviews_by_checklist[key] = kv_client.query_all(
                reviews_coll, {"checklist_id": key}
            )
    except Exception:
        reviews_by_checklist = {}

    summaries: List[Dict[str, Any]] = []
    for checklist in checklists:
        reviews = reviews_by_checklist.get(checklist.get("_key"), [])
        host = hosts.get(checklist.get("host_id"), {})
        baseline = baselines.get(checklist.get("baseline_id"), {})
        collection = collections.get(checklist.get("stig_collection_id"), {})
        package_ids = sorted(
            {
                str(review.get("package_id") or "").strip()
                for review in reviews
                if str(review.get("package_id") or "").strip()
            }
        )
        summaries.append(
            {
                "_key": checklist.get("_key"),
                "title": checklist.get("title"),
                "stig_collection_id": checklist.get("stig_collection_id"),
                "collection_name": collection.get("name") or "",
                "host_id": checklist.get("host_id"),
                "hostname": host.get("hostname") or "",
                "baseline_id": checklist.get("baseline_id"),
                "baseline_title": baseline.get("title") or "",
                "stig_id": baseline.get("stig_id") or "",
                "baseline_version": baseline.get("version") or "",
                "review_count": len(reviews),
                "valid_count": sum(1 for review in reviews if validation.is_valid(review)),
                "package_ids": package_ids,
            }
        )
    summaries.sort(
        key=lambda row: (
            row.get("collection_name") or "",
            row.get("hostname") or "",
            row.get("stig_id") or "",
        )
    )
    return summaries
