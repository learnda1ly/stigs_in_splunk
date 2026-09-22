"""Append-only review change history in KV ``stig_review_history``."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import access
import kv_client
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_HOSTS,
    KV_STIG_REVIEW_HISTORY,
    dumps_json,
    kv_record,
    now_epoch,
)
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import reviews as reviews_svc
import review_workflow

DEFAULT_HISTORY_LIMIT = 100
MAX_HISTORY_LIMIT = 500

TRACKED_FIELDS = (
    "status",
    "finding_details",
    "comments",
    "ingest_lock",
    "workflow_state",
    "package_id",
)

MAX_SUMMARY_LEN = 240
MAX_TEXT_PREVIEW = 80


def _parse_int(value: Any, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    if num < minimum:
        return minimum
    if maximum is not None and num > maximum:
        return maximum
    return num


def _parse_epoch(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes"}


def field_changed(before: Dict[str, Any], after: Dict[str, Any], field: str) -> bool:
    if field == "ingest_lock":
        return _bool_value(before.get(field)) != _bool_value(after.get(field))
    return _text(before.get(field)) != _text(after.get(field))


def changed_field_names(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    return [f for f in TRACKED_FIELDS if field_changed(before, after, f)]


def has_material_change(
    before: Dict[str, Any],
    after: Dict[str, Any],
    *,
    action: Optional[str] = None,
) -> bool:
    if action in ("submit", "accept", "reject"):
        return True
    return bool(changed_field_names(before, after))


def _preview_field(name: str, before: Dict[str, Any], after: Dict[str, Any]) -> str:
    if name in ("finding_details", "comments"):
        old = _text(before.get(name)).strip()
        new = _text(after.get(name)).strip()
        if old == new:
            return f"{name} updated"
        if not old and new:
            return f"{name} set"
        if old and not new:
            return f"{name} cleared"
        return f"{name} updated"
    if name == "ingest_lock":
        new_val = _bool_value(after.get(name))
        return f"ingest_lock={'true' if new_val else 'false'}"
    old = _text(before.get(name))
    new = _text(after.get(name))
    if old == new:
        return f"{name} updated"
    return f"{name}: {old or '—'} → {new or '—'}"


def build_change_summary(
    before: Dict[str, Any],
    after: Dict[str, Any],
    *,
    action: str = "update",
) -> str:
    parts: List[str] = []
    if action in ("submit", "accept", "reject"):
        wf_before = review_workflow.workflow_state(before)
        wf_after = review_workflow.workflow_state(after)
        parts.append(f"workflow: {wf_before} → {wf_after} ({action})")
    elif action == "ingest":
        parts.append("ingest applied")
    elif action == "upgrade":
        parts.append("baseline upgrade")

    for field in changed_field_names(before, after):
        if field == "workflow_state" and action in ("submit", "accept", "reject"):
            continue
        parts.append(_preview_field(field, before, after))

    summary = "; ".join(p for p in parts if p)
    if len(summary) > MAX_SUMMARY_LEN:
        return summary[: MAX_SUMMARY_LEN - 1] + "…"
    return summary or "review updated"


def _context_for_review(
    service,
    review: Dict[str, Any],
    checklist: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    checklist_id = _text(review.get("checklist_id"))
    if checklist is None and checklist_id:
        cl_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
        checklist = kv_client.get_by_key(cl_coll, checklist_id) or {}
    checklist = checklist or {}
    host_id = _text(checklist.get("host_id"))
    return {
        "stig_collection_id": _text(checklist.get("stig_collection_id")),
        "checklist_id": checklist_id,
        "host_id": host_id,
        "baseline_id": _text(review.get("baseline_id") or checklist.get("baseline_id")),
        "group_id": _text(review.get("group_id")),
        "rule_id": _text(review.get("rule_id")),
        "rule_version": _text(review.get("rule_version")),
    }


def record_review_change(
    service,
    before: Dict[str, Any],
    after: Dict[str, Any],
    username: str,
    *,
    action: str = "update",
    checklist: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Insert a history row when assessor-visible fields changed. Best-effort."""
    if not has_material_change(before, after, action=action):
        return None
    review_id = _text(before.get("_key") or after.get("_key"))
    if not review_id:
        return None
    ctx = _context_for_review(service, after, checklist=checklist)
    summary = build_change_summary(before, after, action=action)
    row = {
        "review_id": review_id,
        "stig_collection_id": ctx["stig_collection_id"],
        "checklist_id": ctx["checklist_id"],
        "host_id": ctx["host_id"],
        "baseline_id": ctx["baseline_id"],
        "group_id": ctx["group_id"],
        "rule_id": ctx["rule_id"],
        "rule_version": ctx["rule_version"],
        "action": action,
        "previous_status": _text(before.get("status")),
        "new_status": _text(after.get("status")),
        "previous_workflow_state": review_workflow.workflow_state(before),
        "new_workflow_state": review_workflow.workflow_state(after),
        "changed_fields": dumps_json(changed_field_names(before, after)),
        "summary": summary,
        "actor": username or "unknown",
        "created_at": now_epoch(),
    }
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_HISTORY)
    return kv_client.insert_record(coll, kv_record(row))


def _history_allowed(
    row: Dict[str, Any],
    access_ctx: access.WorkspaceAccess,
    host_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    if access_ctx.admin_bypass:
        return True
    host_id = row.get("host_id") or ""
    baseline_id = row.get("baseline_id") or ""
    if access_ctx.acl_host_ids and host_id not in access_ctx.acl_host_ids:
        return False
    if access_ctx.acl_baseline_ids and baseline_id not in access_ctx.acl_baseline_ids:
        return False
    if access_ctx.acl_label_ids:
        host_by_id = host_by_id or {}
        host = host_by_id.get(host_id)
        if not host:
            return False
        if not access.host_allowed(host, access_ctx):
            return False
    return True


def _public_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    raw = rec.get("changed_fields")
    if isinstance(raw, str) and raw.strip():
        try:
            out["changed_fields"] = json.loads(raw)
        except json.JSONDecodeError:
            out["changed_fields"] = []
    elif not isinstance(raw, list):
        out["changed_fields"] = []
    return out


def list_review_history(
    service,
    review_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    review = reviews_svc.get_review(service, review_id, session)
    if not review:
        raise KeyError(review_id)

    query = query or {}
    limit = _parse_int(
        query.get("limit"), DEFAULT_HISTORY_LIMIT, minimum=1, maximum=MAX_HISTORY_LIMIT
    )
    offset = _parse_int(query.get("offset"), 0, minimum=0)
    since = _parse_epoch(query.get("since") or query.get("created_after"))
    until = _parse_epoch(query.get("until") or query.get("created_before"))

    coll = kv_client.get_collection(service, KV_STIG_REVIEW_HISTORY)
    rows = kv_client.query_all(coll, {"review_id": review_id})
    rows = [_public_row(r) for r in rows]
    if since is not None:
        rows = [r for r in rows if float(r.get("created_at") or 0) >= since]
    if until is not None:
        rows = [r for r in rows if float(r.get("created_at") or 0) <= until]
    rows.sort(key=lambda r: float(r.get("created_at") or 0), reverse=True)
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "review_id": review_id,
        "history": page,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(page) < total,
        },
    }


def _require_read_collection(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    grants = grants_svc.query_grants(service, collection_id)
    if not access.user_can_read_collection(rec, session, grants):
        raise KeyError(collection_id)
    return rec


def list_collection_review_history(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    query = query or {}
    collection = _require_read_collection(service, collection_id, session)
    _rec, access_ctx, _grants = grants_svc.workspace_context(
        service, collection_id, session
    )

    limit = _parse_int(
        query.get("limit"), DEFAULT_HISTORY_LIMIT, minimum=1, maximum=MAX_HISTORY_LIMIT
    )
    offset = _parse_int(query.get("offset"), 0, minimum=0)
    since = _parse_epoch(query.get("since") or query.get("created_after"))
    until = _parse_epoch(query.get("until") or query.get("created_before"))

    host_id_filter = _text(query.get("host_id")).strip()
    baseline_filter = _text(query.get("baseline_id")).strip()
    rule_id_filter = _text(query.get("rule_id")).strip()
    review_id_filter = _text(query.get("review_id")).strip()

    host_by_id: Dict[str, Dict[str, Any]] = {}
    if access_ctx.acl_label_ids:
        host_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
        for host in kv_client.query_all(host_coll, {"stig_collection_id": collection_id}):
            key = host.get("_key")
            if key:
                host_by_id[str(key)] = host

    coll = kv_client.get_collection(service, KV_STIG_REVIEW_HISTORY)
    rows = kv_client.query_all(coll, {"stig_collection_id": collection_id})
    filtered: List[Dict[str, Any]] = []
    for rec in rows:
        if review_id_filter and rec.get("review_id") != review_id_filter:
            continue
        if host_id_filter and rec.get("host_id") != host_id_filter:
            continue
        if baseline_filter and rec.get("baseline_id") != baseline_filter:
            continue
        if rule_id_filter and rec.get("rule_id") != rule_id_filter:
            continue
        ts = float(rec.get("created_at") or 0)
        if since is not None and ts < since:
            continue
        if until is not None and ts > until:
            continue
        if not _history_allowed(rec, access_ctx, host_by_id):
            continue
        filtered.append(_public_row(rec))

    filtered.sort(key=lambda r: float(r.get("created_at") or 0), reverse=True)
    total = len(filtered)
    page = filtered[offset : offset + limit]
    return {
        "stig_collection_id": collection_id,
        "stig_collection_name": collection.get("name"),
        "history": page,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(page) < total,
        },
        "filters": {
            "host_id": host_id_filter or None,
            "baseline_id": baseline_filter or None,
            "rule_id": rule_id_filter or None,
            "review_id": review_id_filter or None,
            "since": since,
            "until": until,
        },
    }


def delete_history_for_collection(service, collection_id: str) -> int:
    """Remove history rows when a workspace is cascade-deleted."""
    coll = kv_client.get_collection(service, KV_STIG_REVIEW_HISTORY)
    removed = 0
    for rec in kv_client.query_all(coll, {"stig_collection_id": collection_id}):
        kv_client.delete_record(coll, rec["_key"])
        removed += 1
    return removed
