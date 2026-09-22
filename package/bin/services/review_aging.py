"""Per-workspace review aging policy and stale review reporting."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import audit
import kv_client
import review_workflow
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_COLLECTIONS,
    KV_STIG_HOSTS,
    KV_STIG_REVIEWS,
    STATUSES,
    dumps_json,
    kv_record,
    now_epoch,
    parse_json_field,
)
from services import baselines as baselines_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import reporting as reporting_svc

REVIEW_AGING_FIELD = "review_aging_config"

CONFIG_FIELD_NAMES = (
    "enabled",
    "stale_after_days",
    "stale_after_hours",
    "statuses",
    "workflow_states",
    "severities",
)

ALLOWED_SEVERITIES = frozenset({"high", "medium", "low", "unknown"})
DEFAULT_STATUSES = ("open", "not_a_finding", "not_applicable")
DEFAULT_WORKFLOW_STATES = tuple(review_workflow.WORKFLOW_STATES)


def default_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "stale_after_days": 90,
        "stale_after_hours": None,
        "statuses": list(DEFAULT_STATUSES),
        "workflow_states": list(DEFAULT_WORKFLOW_STATES),
        "severities": [],
    }


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_positive_int(value: Any, field: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a positive integer")
    if parsed <= 0:
        raise ValueError(f"{field} must be > 0")
    return parsed


def _normalize_string_list(
    raw: Any,
    *,
    allowed: Optional[Set[str]] = None,
    field: str,
) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array")
    out: List[str] = []
    for item in raw:
        key = str(item or "").strip().lower()
        if not key:
            continue
        if allowed is not None and key not in allowed:
            raise ValueError(f"invalid value in {field}: {item}")
        if key not in out:
            out.append(key)
    return out


def normalize_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out = default_config()
    out["enabled"] = _as_bool(src.get("enabled"), out["enabled"])
    if "stale_after_days" in src:
        days = _as_positive_int(src.get("stale_after_days"), "stale_after_days")
        if days is not None:
            out["stale_after_days"] = days
    if "stale_after_hours" in src:
        hours = src.get("stale_after_hours")
        if hours is None or hours == "":
            out["stale_after_hours"] = None
        else:
            out["stale_after_hours"] = _as_positive_int(hours, "stale_after_hours")
    if "statuses" in src:
        statuses = _normalize_string_list(
            src.get("statuses"), allowed=set(STATUSES), field="statuses"
        )
        out["statuses"] = statuses or list(DEFAULT_STATUSES)
    if "workflow_states" in src:
        wf = _normalize_string_list(
            src.get("workflow_states"),
            allowed=set(review_workflow.WORKFLOW_STATES),
            field="workflow_states",
        )
        out["workflow_states"] = wf or list(DEFAULT_WORKFLOW_STATES)
    if "severities" in src:
        out["severities"] = _normalize_string_list(
            src.get("severities"), allowed=ALLOWED_SEVERITIES, field="severities"
        )
    return out


def parse_config_from_collection(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = parse_json_field((rec or {}).get(REVIEW_AGING_FIELD), default={}) or {}
    if not isinstance(raw, dict):
        return default_config()
    return normalize_config(raw)


def stale_threshold_seconds(config: Dict[str, Any]) -> int:
    hours = config.get("stale_after_hours")
    if hours is not None and int(hours) > 0:
        return int(hours) * 3600
    days = int(config.get("stale_after_days") or 90)
    return days * 86400


def review_last_change_epoch(review: Dict[str, Any]) -> float:
    """Material change time for aging (review KV updated_at)."""
    try:
        return float(review.get("updated_at") or 0)
    except (TypeError, ValueError):
        return 0.0


def review_matches_aging_filters(
    review: Dict[str, Any],
    config: Dict[str, Any],
    severity: str,
) -> bool:
    status = (review.get("status") or "not_reviewed").strip().lower()
    if status not in set(config.get("statuses") or []):
        return False
    wf = review_workflow.workflow_state(review)
    if wf not in set(config.get("workflow_states") or []):
        return False
    sev_filter = config.get("severities") or []
    if sev_filter:
        sev = (severity or "unknown").strip().lower()
        if sev not in set(sev_filter):
            return False
    return True


def is_review_stale(
    review: Dict[str, Any],
    config: Dict[str, Any],
    *,
    severity: str,
    now: Optional[float] = None,
) -> bool:
    if not config.get("enabled"):
        return False
    if not review_matches_aging_filters(review, config, severity):
        return False
    ts = review_last_change_epoch(review)
    if ts <= 0:
        return False
    cutoff = (now if now is not None else now_epoch()) - stale_threshold_seconds(config)
    return ts < cutoff


def _require_write(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not ctx.can_write:
        raise PermissionError("access denied to stig_collection")
    return rec


def _require_read(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not ctx.can_read:
        raise KeyError(collection_id)
    return rec


def get_config(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    rec = _require_read(service, collection_id, session)
    config = parse_config_from_collection(rec)
    return {
        "stig_collection_id": collection_id,
        "review_aging": config,
        "defaults": default_config(),
        "stale_threshold_seconds": stale_threshold_seconds(config),
    }


def patch_config(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    incoming = body.get("review_aging")
    if incoming is None and any(k in body for k in CONFIG_FIELD_NAMES):
        incoming = body
    if not isinstance(incoming, dict):
        raise ValueError("review_aging object is required")
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    merged = parse_config_from_collection(rec)
    for key in CONFIG_FIELD_NAMES:
        if key in incoming:
            merged[key] = incoming[key]
    config = normalize_config(merged)
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    patch = dict(rec)
    patch[REVIEW_AGING_FIELD] = dumps_json(config)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, collection_id, kv_record(patch))
    audit.log_event(
        "update",
        "stig_collection_review_aging",
        collection_id,
        username,
        {"review_aging": config},
    )
    return {
        "stig_collection_id": collection_id,
        "review_aging": config,
        "stale_threshold_seconds": stale_threshold_seconds(config),
        "collection": stored,
    }


def _parse_limit(query: Optional[Dict[str, Any]], default: int = 500) -> int:
    query = query or {}
    try:
        limit = int(query.get("limit") or default)
    except (TypeError, ValueError):
        limit = default
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000
    return limit


def _stale_row(
    review: Dict[str, Any],
    *,
    checklist: Dict[str, Any],
    host: Dict[str, Any],
    baseline: Dict[str, Any],
    severity: str,
    config: Dict[str, Any],
    now: float,
) -> Dict[str, Any]:
    updated = review_last_change_epoch(review)
    age_seconds = max(0, int(now - updated)) if updated else None
    row = reporting_svc._enrich_finding(
        review,
        checklist=checklist,
        host=host,
        baseline=baseline,
        severity=severity,
    )
    row["workflow_state"] = review_workflow.workflow_state(review)
    row["aging_stale"] = True
    row["aging_last_change_at"] = updated
    row["aging_age_seconds"] = age_seconds
    row["aging_threshold_seconds"] = stale_threshold_seconds(config)
    return row


def list_stale_reviews(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rec = _require_read(service, collection_id, session)
    config = parse_config_from_collection(rec)
    now = now_epoch()
    limit = _parse_limit(query)
    if not config.get("enabled"):
        return {
            "stig_collection_id": collection_id,
            "review_aging": config,
            "enabled": False,
            "stale_count": 0,
            "stale_threshold_seconds": stale_threshold_seconds(config),
            "generated_at": now,
            "items": [],
        }

    ctx = reporting_svc._collection_workspace_context(service, collection_id, session)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    items: List[Dict[str, Any]] = []
    stale_count = 0
    for checklist_id, checklist in ctx["checklist_by_id"].items():
        host = ctx["host_by_id"].get(checklist.get("host_id") or "", {})
        baseline = ctx["baselines"].get(checklist.get("baseline_id") or "", {})
        for review in kv_client.query_all(reviews_coll, {"checklist_id": checklist_id}):
            sev = reporting_svc.review_severity(review, ctx["severity_index"])
            if not is_review_stale(review, config, severity=sev, now=now):
                continue
            stale_count += 1
            if len(items) < limit:
                items.append(
                    _stale_row(
                        review,
                        checklist=checklist,
                        host=host,
                        baseline=baseline,
                        severity=sev,
                        config=config,
                        now=now,
                    )
                )

    return {
        "stig_collection_id": collection_id,
        "review_aging": config,
        "enabled": True,
        "stale_count": stale_count,
        "stale_threshold_seconds": stale_threshold_seconds(config),
        "generated_at": now,
        "limit": limit,
        "items": items,
    }


def report_stale_all_workspaces(service) -> Dict[str, Any]:
    """Unfiltered stale rows for scheduled search / admin report (not grant-scoped)."""
    now = now_epoch()
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    rows: List[Dict[str, Any]] = []
    workspaces_scanned = 0
    for collection in collections_svc.list_all_collections(service):
        collection_id = collection.get("_key")
        if not collection_id:
            continue
        config = parse_config_from_collection(collection)
        if not config.get("enabled"):
            continue
        workspaces_scanned += 1
        checklists = kv_client.query_all(
            kv_client.get_collection(service, KV_STIG_CHECKLISTS),
            {"stig_collection_id": collection_id},
        )
        host_by_id = {
            h["_key"]: h
            for h in kv_client.query_all(
                kv_client.get_collection(service, KV_STIG_HOSTS),
                {"stig_collection_id": collection_id},
            )
            if h.get("_key")
        }
        baselines = {
            b["_key"]: b
            for b in baselines_svc.list_baselines(service)
            if b.get("_key")
        }
        baseline_ids = {c.get("baseline_id") for c in checklists if c.get("baseline_id")}
        rule_meta_index = reporting_svc._rule_meta_index(service, baseline_ids)
        severity_index = reporting_svc._severity_index_from_meta(rule_meta_index)
        checklist_by_id = {c["_key"]: c for c in checklists if c.get("_key")}

        for checklist_id, checklist in checklist_by_id.items():
            host = host_by_id.get(checklist.get("host_id") or "", {})
            baseline = baselines.get(checklist.get("baseline_id") or "", {})
            for review in kv_client.query_all(reviews_coll, {"checklist_id": checklist_id}):
                sev = reporting_svc.review_severity(review, severity_index)
                if not is_review_stale(review, config, severity=sev, now=now):
                    continue
                row = _stale_row(
                    review,
                    checklist=checklist,
                    host=host,
                    baseline=baseline,
                    severity=sev,
                    config=config,
                    now=now,
                )
                row["collection_name"] = collection.get("name") or ""
                rows.append(row)

    return {
        "generated_at": now,
        "workspaces_scanned": workspaces_scanned,
        "stale_count": len(rows),
        "items": rows,
        "note": (
            "Report is not grant-filtered; use GET "
            "/stig_collections/{id}/review_aging/stale for ACL-scoped results."
        ),
    }
