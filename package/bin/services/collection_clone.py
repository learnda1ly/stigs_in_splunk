"""Clone a workspace (stig_collection) and optional scoped data."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import access
import audit
import kv_client
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_COLLECTION_GRANTS,
    KV_STIG_HOSTS,
    KV_STIG_LABELS,
    KV_STIG_REVIEWS,
    dumps_json,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)
from services import baseline_defaults as baseline_defaults_svc
from services import baselines as baselines_svc
from services import collection_metadata as collection_metadata_svc
from services import collections as collections_svc
from services import grants as grants_svc

logger = logging.getLogger("stigs_in_splunk.collection_clone")

# Boolean clone flags default when omitted from the request body.
DEFAULT_COPY_HOSTS = True
DEFAULT_COPY_CHECKLISTS = True
DEFAULT_COPY_REVIEWS = True
DEFAULT_COPY_GRANTS = False
DEFAULT_COPY_LABELS = True
DEFAULT_COPY_METADATA = True
DEFAULT_COPY_BASELINE_DEFAULTS = True
DEFAULT_COPY_REVIEW_REQUIREMENTS = True
DEFAULT_PIN_ALL_STIGS_TO_DEFAULTS = False

_COLLECTION_SKIP_KEYS = frozenset(
    {"_key", "created_at", "updated_at", "created_by", "updated_by", "is_default"}
)


def _flag(body: Dict[str, Any], key: str, default: bool) -> bool:
    options = body.get("options")
    if isinstance(options, dict) and key in options:
        return collections_svc.parse_cascade_flag(options.get(key))
    if key in body:
        return collections_svc.parse_cascade_flag(body.get(key))
    return default


def _flag_explicit(body: Dict[str, Any], key: str) -> bool:
    if key in body:
        return True
    options = body.get("options")
    return isinstance(options, dict) and key in options


def _raw_flags(body: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "copy_hosts": _flag(body, "copy_hosts", DEFAULT_COPY_HOSTS),
        "copy_checklists": _flag(body, "copy_checklists", DEFAULT_COPY_CHECKLISTS),
        "copy_reviews": _flag(body, "copy_reviews", DEFAULT_COPY_REVIEWS),
        "copy_grants": _flag(body, "copy_grants", DEFAULT_COPY_GRANTS),
        "copy_labels": _flag(body, "copy_labels", DEFAULT_COPY_LABELS),
        "copy_metadata": _flag(body, "copy_metadata", DEFAULT_COPY_METADATA),
        "copy_baseline_defaults": _flag(
            body, "copy_baseline_defaults", DEFAULT_COPY_BASELINE_DEFAULTS
        ),
        "copy_review_requirements": _flag(
            body, "copy_review_requirements", DEFAULT_COPY_REVIEW_REQUIREMENTS
        ),
        "copy_import_options": _flag(
            body, "copy_import_options", DEFAULT_COPY_REVIEW_REQUIREMENTS
        ),
        "pin_all_stigs_to_defaults": _flag(
            body, "pin_all_stigs_to_defaults", DEFAULT_PIN_ALL_STIGS_TO_DEFAULTS
        ),
    }


def parse_clone_options(body: Dict[str, Any]) -> Tuple[Dict[str, bool], List[str]]:
    body = body or {}
    raw = _raw_flags(body)
    copy_hosts = raw["copy_hosts"]
    copy_checklists = raw["copy_checklists"]
    copy_reviews = raw["copy_reviews"]
    copy_grants = raw["copy_grants"]
    copy_labels = raw["copy_labels"]
    copy_metadata = raw["copy_metadata"]
    copy_baseline_defaults = raw["copy_baseline_defaults"]
    copy_review_requirements = raw["copy_review_requirements"]
    copy_import_options = raw["copy_import_options"]

    # STIG Manager compatibility aliases
    stig_mappings = (
        body.get("options", {}).get("stigMappings")
        if isinstance(body.get("options"), dict)
        else body.get("stigMappings")
    )
    if stig_mappings == "withoutReviews":
        copy_reviews = False
    elif stig_mappings == "withReviews":
        copy_reviews = True
    if isinstance(body.get("options"), dict) and "grants" in body["options"]:
        copy_grants = collections_svc.parse_cascade_flag(body["options"].get("grants"))
    pin_all_stigs_to_defaults = raw["pin_all_stigs_to_defaults"]
    options = body.get("options")
    if isinstance(options, dict) and "pinAllStigsToDefaults" in options:
        pin_all_stigs_to_defaults = collections_svc.parse_cascade_flag(
            options.get("pinAllStigsToDefaults")
        )

    coerced: List[str] = []
    before_checklists = copy_checklists
    before_reviews = copy_reviews

    if not copy_hosts:
        copy_checklists = False
    if not copy_checklists:
        copy_reviews = False

    if before_checklists and not copy_checklists:
        coerced.append("copy_checklists forced false because copy_hosts is false")
    if before_reviews and not copy_reviews:
        coerced.append("copy_reviews forced false because copy_checklists is false")

    before_baseline_defaults = copy_baseline_defaults
    if pin_all_stigs_to_defaults:
        copy_baseline_defaults = True
    if pin_all_stigs_to_defaults and not before_baseline_defaults:
        coerced.append(
            "copy_baseline_defaults forced true because pin_all_stigs_to_defaults is true"
        )

    opts = {
        "copy_hosts": copy_hosts,
        "copy_checklists": copy_checklists,
        "copy_reviews": copy_reviews,
        "copy_grants": copy_grants,
        "copy_labels": copy_labels,
        "copy_metadata": copy_metadata,
        "copy_baseline_defaults": copy_baseline_defaults,
        "copy_review_requirements": copy_review_requirements,
        "copy_import_options": copy_import_options,
        "pin_all_stigs_to_defaults": pin_all_stigs_to_defaults,
    }
    return opts, coerced


def validate_clone_request(
    body: Dict[str, Any],
    opts: Dict[str, bool],
    source_grants: List[Dict[str, Any]],
) -> None:
    """Reject contradictory flag combinations and unsafe grant copies."""
    body = body or {}
    raw = _raw_flags(body)

    if _flag_explicit(body, "copy_checklists") and raw["copy_checklists"] and not opts["copy_checklists"]:
        raise ValueError("copy_checklists requires copy_hosts true")
    if _flag_explicit(body, "copy_reviews") and raw["copy_reviews"] and not opts["copy_reviews"]:
        raise ValueError("copy_reviews requires copy_hosts and copy_checklists true")
    if opts["pin_all_stigs_to_defaults"] and not opts["copy_checklists"]:
        if _flag_explicit(body, "pin_all_stigs_to_defaults") or (
            isinstance(body.get("options"), dict)
            and "pinAllStigsToDefaults" in body["options"]
        ):
            raise ValueError(
                "pin_all_stigs_to_defaults requires copy_checklists true"
            )

    if not opts["copy_grants"]:
        return

    for rec in source_grants:
        acl_hosts = grants_svc.normalize_acl_id_list(rec.get("acl_host_ids"))
        acl_labels = grants_svc.normalize_acl_id_list(rec.get("acl_labels"))
        grant_id = rec.get("_key") or rec.get("principal") or "grant"
        if acl_hosts and not opts["copy_hosts"]:
            raise ValueError(
                "copy_grants requires copy_hosts true when source grants use acl_host_ids "
                f"(grant {grant_id})"
            )
        if acl_labels and not opts["copy_labels"]:
            raise ValueError(
                "copy_grants requires copy_labels true when source grants use acl_labels "
                f"(grant {grant_id})"
            )


def _remap_acl_ids(
    source_ids: List[str], id_map: Dict[str, str], dimension: str
) -> List[str]:
    if not source_ids:
        return []
    remapped: List[str] = []
    missing: List[str] = []
    for sid in source_ids:
        mapped = id_map.get(sid)
        if mapped:
            remapped.append(mapped)
        else:
            missing.append(sid)
    if missing:
        raise ValueError(
            f"grant_acl_remap_failed: {dimension} id(s) not copied to clone: "
            + ", ".join(sorted(missing))
        )
    return remapped


def _unique_workspace_name(service, desired: str) -> str:
    base = (desired or "").strip() or "Untitled"
    if not collections_svc.find_collection_by_name(service, base):
        return base
    for suffix in range(2, 10_000):
        candidate = f"{base} ({suffix})"
        if not collections_svc.find_collection_by_name(service, candidate):
            return candidate
    raise ValueError("could not allocate unique workspace name")


def _pin_cloned_checklists_to_source_defaults(
    service,
    source_collection_id: str,
    checklist_map: Dict[str, str],
    username: str,
    ts: int,
) -> int:
    """Set each cloned checklist baseline to the source workspace default pin map."""
    if not checklist_map:
        return 0
    cl_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    pinned = 0
    for _old_cl, new_cl in checklist_map.items():
        rec = kv_client.get_by_key(cl_coll, new_cl)
        if not rec:
            continue
        baseline_id = (rec.get("baseline_id") or "").strip()
        baseline = baselines_svc.get_baseline(service, baseline_id) if baseline_id else None
        if not baseline:
            continue
        stig_id = str(baseline.get("stig_id") or "")
        xccdf_id = str(baseline.get("xccdf_benchmark_id") or "")
        default_bid = baseline_defaults_svc.lookup_default_baseline_id(
            service, source_collection_id, stig_id, xccdf_id
        )
        if not default_bid:
            continue
        if default_bid == baseline_id:
            pinned += 1
            continue
        patched = dict(rec)
        patched["baseline_id"] = default_bid
        patched["updated_at"] = ts
        patched["updated_by"] = username
        kv_client.update_record(cl_coll, new_cl, kv_record(patched))
        pinned += 1
    return pinned


def _clone_row(
    rec: Dict[str, Any],
    *,
    username: str,
    ts: int,
    overrides: Dict[str, Any],
    skip: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    skip_keys = _COLLECTION_SKIP_KEYS | (skip or set())
    row = {k: v for k, v in rec.items() if k not in skip_keys}
    row.update(overrides)
    row["created_at"] = ts
    row["updated_at"] = ts
    row["created_by"] = username
    row["updated_by"] = username
    return kv_record(row)


def validate_clone_job_request(
    service,
    source_collection_id: str,
    body: Dict[str, Any],
    session: Dict[str, Any],
) -> None:
    """ACL and flag validation for async clone jobs (no destination created)."""
    src_id = (source_collection_id or "").strip()
    if not src_id:
        raise ValueError("source workspace id is required")
    grants_svc.require_workspace_read(service, src_id, session)
    if not access.user_has_stig_write(session):
        raise PermissionError("stig_write required to clone a workspace")
    source = collections_svc.get_collection(service, src_id)
    if not source:
        raise KeyError(src_id)
    opts, _coerced = parse_clone_options(body or {})
    source_grants = grants_svc.query_grants(service, src_id)
    validate_clone_request(body or {}, opts, source_grants)


def clone_collection(
    service,
    source_collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Clone ``source_collection_id`` into a new workspace.

    Requires read access to the source workspace and ``stig_write`` (or admin)
    to create the destination. Global ``stig_baselines`` are never copied.
    """
    src_id = (source_collection_id or "").strip()
    if not src_id:
        raise ValueError("source workspace id is required")

    validate_clone_job_request(service, src_id, body, session)
    source = collections_svc.get_collection(service, src_id)
    if not source:
        raise KeyError(src_id)

    body = body or {}
    opts, coerced_warnings = parse_clone_options(body)
    source_grants = grants_svc.query_grants(service, src_id)
    validate_clone_request(body, opts, source_grants)

    source_name = (source.get("name") or src_id).strip()
    dest_name = _unique_workspace_name(
        service, (body.get("name") or f"{source_name} (clone)").strip()
    )
    description = body.get("description")
    if description is None:
        description = source.get("description") or ""

    dest_body: Dict[str, Any] = {
        "name": dest_name,
        "description": description,
        "is_default": False,
    }
    if "access_principals" in body:
        dest_body["access_principals"] = body.get("access_principals")

    dest = collections_svc.create_collection(service, dest_body, username)
    dest_id = dest["_key"]
    ts = now_epoch()

    summary = {
        "labels": 0,
        "hosts": 0,
        "checklists": 0,
        "reviews": 0,
        "grants": 0,
        "pinned_checklists": 0,
    }
    label_map: Dict[str, str] = {}
    host_map: Dict[str, str] = {}
    checklist_map: Dict[str, str] = {}

    try:
        patch: Dict[str, Any] = {}
        if opts["copy_metadata"]:
            metadata = collection_metadata_svc.parse_metadata_from_collection(source)
            if metadata:
                patch[collection_metadata_svc.METADATA_FIELD] = dumps_json(metadata)
        if opts["copy_baseline_defaults"] and source.get("default_baseline_map"):
            patch["default_baseline_map"] = source.get("default_baseline_map")
        if opts["copy_review_requirements"]:
            if source.get("review_requirements"):
                patch["review_requirements"] = source.get("review_requirements")
            if source.get("review_accept_principals"):
                patch["review_accept_principals"] = source.get("review_accept_principals")
        if opts["copy_import_options"] and source.get("import_options"):
            patch["import_options"] = source.get("import_options")
        if patch:
            dest = collections_svc.update_collection(service, dest_id, patch, username)

        if opts["copy_labels"]:
            labels_coll = kv_client.get_collection(service, KV_STIG_LABELS)
            for rec in kv_client.query_all(
                labels_coll, {"stig_collection_id": src_id}
            ):
                new_key = new_id()
                stored = kv_client.insert_record(
                    labels_coll,
                    _clone_row(
                        rec,
                        username=username,
                        ts=ts,
                        overrides={
                            "_key": new_key,
                            "stig_collection_id": dest_id,
                        },
                    ),
                )
                label_map[rec["_key"]] = stored["_key"]
                summary["labels"] += 1

        if opts["copy_hosts"]:
            hosts_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
            for rec in kv_client.query_all(
                hosts_coll, {"stig_collection_id": src_id}
            ):
                new_key = new_id()
                label_ids = parse_json_field(rec.get("label_ids"), default=[])
                if not isinstance(label_ids, list):
                    label_ids = []
                if opts["copy_labels"]:
                    remapped = [
                        label_map[str(lid)]
                        for lid in label_ids
                        if str(lid) in label_map
                    ]
                else:
                    remapped = []
                stored = kv_client.insert_record(
                    hosts_coll,
                    _clone_row(
                        rec,
                        username=username,
                        ts=ts,
                        overrides={
                            "_key": new_key,
                            "stig_collection_id": dest_id,
                            "label_ids": dumps_json(remapped),
                        },
                    ),
                )
                host_map[rec["_key"]] = stored["_key"]
                summary["hosts"] += 1
                audit.log_event(
                    "create",
                    "stig_host",
                    new_key,
                    username,
                    {
                        "stig_collection_id": dest_id,
                        "cloned_from": rec["_key"],
                        "source_stig_collection_id": src_id,
                    },
                )

        if opts["copy_checklists"]:
            cl_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
            for rec in kv_client.query_all(
                cl_coll, {"stig_collection_id": src_id}
            ):
                old_host = rec.get("host_id") or ""
                if old_host not in host_map:
                    continue
                new_key = new_id()
                stored = kv_client.insert_record(
                    cl_coll,
                    _clone_row(
                        rec,
                        username=username,
                        ts=ts,
                        overrides={
                            "_key": new_key,
                            "stig_collection_id": dest_id,
                            "host_id": host_map[old_host],
                        },
                    ),
                )
                checklist_map[rec["_key"]] = stored["_key"]
                summary["checklists"] += 1

        if opts["pin_all_stigs_to_defaults"] and checklist_map:
            summary["pinned_checklists"] = _pin_cloned_checklists_to_source_defaults(
                service,
                src_id,
                checklist_map,
                username,
                ts,
            )

        if opts["copy_reviews"]:
            reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
            for old_cl, new_cl in checklist_map.items():
                for rec in kv_client.query_all(
                    reviews_coll, {"checklist_id": old_cl}
                ):
                    new_key = new_id()
                    kv_client.insert_record(
                        reviews_coll,
                        _clone_row(
                            rec,
                            username=username,
                            ts=ts,
                            overrides={
                                "_key": new_key,
                                "checklist_id": new_cl,
                                "stig_collection_id": dest_id,
                            },
                        ),
                    )
                    summary["reviews"] += 1

        if opts["copy_grants"]:
            grants_coll = kv_client.get_collection(service, KV_STIG_COLLECTION_GRANTS)
            principals_added: List[str] = []
            for rec in source_grants:
                new_key = new_id()
                acl_hosts = grants_svc.normalize_acl_id_list(rec.get("acl_host_ids"))
                acl_labels = grants_svc.normalize_acl_id_list(rec.get("acl_labels"))
                remapped_hosts = _remap_acl_ids(acl_hosts, host_map, "acl_host_ids")
                remapped_labels = _remap_acl_ids(acl_labels, label_map, "acl_labels")
                grant_row = _clone_row(
                    rec,
                    username=username,
                    ts=ts,
                    overrides={
                        "_key": new_key,
                        "stig_collection_id": dest_id,
                        "acl_host_ids": dumps_json(remapped_hosts),
                        "acl_baseline_ids": rec.get("acl_baseline_ids") or "[]",
                        "acl_labels": dumps_json(remapped_labels),
                    },
                )
                kv_client.insert_record(grants_coll, grant_row)
                principal = (rec.get("principal") or "").strip()
                if principal:
                    principals_added.append(principal)
                summary["grants"] += 1
            if principals_added:
                dest_rec = collections_svc.get_collection(service, dest_id) or dest
                principals = access.parse_access_principals(
                    dest_rec.get("access_principals")
                )
                for principal in principals_added:
                    if principal not in principals:
                        principals.append(principal)
                collections_svc.update_collection(
                    service,
                    dest_id,
                    {"access_principals": principals},
                    username,
                )

        audit.log_event(
            "clone",
            "stig_collection",
            dest_id,
            username,
            {
                "source_stig_collection_id": src_id,
                "options": opts,
                "summary": summary,
            },
        )
        result: Dict[str, Any] = {
            "source_stig_collection_id": src_id,
            "stig_collection": dest,
            "stig_collection_id": dest_id,
            "options": opts,
            "summary": summary,
            "id_map": {
                "labels": label_map,
                "hosts": host_map,
                "checklists": checklist_map,
            },
        }
        if coerced_warnings:
            result["options_coerced"] = coerced_warnings
        return result
    except Exception as exc:
        rollback_error: Optional[BaseException] = None
        try:
            collections_svc.delete_collection(
                service, dest_id, username, cascade=True, source="clone_rollback"
            )
        except Exception as rb_exc:
            rollback_error = rb_exc
            audit.log_event(
                "clone_rollback_failed",
                "stig_collection",
                dest_id,
                username,
                {
                    "source_stig_collection_id": src_id,
                    "clone_error": str(exc),
                    "rollback_error": str(rb_exc),
                },
            )
            logger.exception(
                "clone rollback failed for workspace %s after %s",
                dest_id,
                exc,
            )
        if rollback_error is not None:
            raise RuntimeError(
                f"clone failed ({exc}); rollback also failed ({rollback_error})"
            ) from exc
        raise
