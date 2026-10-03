"""Per-workspace review aging policy and stale review reporting."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import audit
import kv_client
import review_workflow
from models import (
    KV_STIG_COLLECTIONS,
    KV_STIG_EDITOR_SETTINGS,
    KV_STIG_REVIEWS,
    STATUSES,
    dumps_json,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)
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
    "rules",
)

TRIGGER_FIELDS = frozenset({"ts", "status_ts", "touch_ts"})
TARGET_TYPES = frozenset(
    {"collection", "asset", "asset_stig", "label", "label_stig", "stig"}
)
ACTION_TYPES = frozenset(
    {
        "delete",
        "set_status_saved",
        "set_status_submitted",
        "set_result_not_checked",
        "set_result_informational",
    }
)

JOB_ENABLED_FIELD = "review_aging_job_enabled"
JOB_LAST_RUN_FIELD = "review_aging_job_last_run"

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
        "rules": [],
    }


def default_rule() -> Dict[str, Any]:
    return {
        "id": "",
        "ordinal": 0,
        "enabled": False,
        "trigger_field": "touch_ts",
        "interval_days": 90,
        "interval_hours": None,
        "interval_minutes": None,
        "interval_seconds": None,
        "action": "set_status_saved",
        "target": {"type": "collection"},
        "statuses": list(DEFAULT_STATUSES),
        "workflow_states": list(DEFAULT_WORKFLOW_STATES),
        "severities": [],
    }


def _truthy_flag(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


def _normalize_interval_component(
    value: Any, field: str
) -> Optional[int]:
    if value is None or value == "":
        return None
    parsed = _as_positive_int(value, field)
    return parsed


def _normalize_target(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    ttype = str(src.get("type") or "collection").strip().lower()
    if ttype not in TARGET_TYPES:
        raise ValueError(f"invalid target.type: {src.get('type')}")
    out: Dict[str, Any] = {"type": ttype}
    for key in ("host_id", "baseline_id", "label_id"):
        if key in src:
            out[key] = str(src.get(key) or "").strip()
    if ttype == "asset" and not out.get("host_id"):
        raise ValueError("target.host_id is required for asset target")
    if ttype == "asset_stig" and (
        not out.get("host_id") or not out.get("baseline_id")
    ):
        raise ValueError("target.host_id and target.baseline_id required for asset_stig")
    if ttype == "stig" and not out.get("baseline_id"):
        raise ValueError("target.baseline_id is required for stig target")
    if ttype == "label" and not out.get("label_id"):
        raise ValueError("target.label_id is required for label target")
    if ttype == "label_stig" and (
        not out.get("label_id") or not out.get("baseline_id")
    ):
        raise ValueError("target.label_id and target.baseline_id required for label_stig")
    return out


def normalize_rule(raw: Optional[Dict[str, Any]], *, ordinal: int = 0) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out = default_rule()
    out["ordinal"] = ordinal
    rid = str(src.get("id") or "").strip()
    out["id"] = rid or new_id()
    out["enabled"] = _as_bool(src.get("enabled"), out["enabled"])
    trigger = str(src.get("trigger_field") or out["trigger_field"]).strip().lower()
    if trigger not in TRIGGER_FIELDS:
        raise ValueError(f"invalid trigger_field: {src.get('trigger_field')}")
    out["trigger_field"] = trigger
    if "interval_days" in src:
        days = _normalize_interval_component(src.get("interval_days"), "interval_days")
        if days is not None:
            out["interval_days"] = days
    if "interval_hours" in src:
        out["interval_hours"] = _normalize_interval_component(
            src.get("interval_hours"), "interval_hours"
        )
    if "interval_minutes" in src:
        out["interval_minutes"] = _normalize_interval_component(
            src.get("interval_minutes"), "interval_minutes"
        )
    if "interval_seconds" in src:
        out["interval_seconds"] = _normalize_interval_component(
            src.get("interval_seconds"), "interval_seconds"
        )
    action = str(src.get("action") or out["action"]).strip().lower()
    if action not in ACTION_TYPES:
        raise ValueError(f"invalid action: {src.get('action')}")
    out["action"] = action
    if "target" in src:
        out["target"] = _normalize_target(src.get("target"))
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
    if "ordinal" in src:
        try:
            out["ordinal"] = int(src.get("ordinal"))
        except (TypeError, ValueError):
            raise ValueError("ordinal must be an integer")
    if rule_interval_seconds(out) <= 0:
        raise ValueError("rule interval must be > 0 seconds")
    return out


def normalize_rules(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("rules must be an array")
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw):
        rule = normalize_rule(item if isinstance(item, dict) else {}, ordinal=idx)
        out.append(rule)
    return out


def rule_interval_seconds(rule: Dict[str, Any]) -> int:
    for key, mult in (
        ("interval_seconds", 1),
        ("interval_minutes", 60),
        ("interval_hours", 3600),
        ("interval_days", 86400),
    ):
        val = rule.get(key)
        if val is not None and int(val) > 0:
            return int(val) * mult
    return int(rule.get("interval_days") or 90) * 86400


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
    if "rules" in src:
        out["rules"] = normalize_rules(src.get("rules"))
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
        "default_rule": default_rule(),
        "stale_threshold_seconds": stale_threshold_seconds(config),
        "action_types": sorted(ACTION_TYPES),
        "target_types": sorted(TARGET_TYPES),
        "trigger_fields": sorted(TRIGGER_FIELDS),
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


def report_stale_all_workspaces(
    service,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Stale rows for grant-visible workspaces (scheduled search / multi-workspace report)."""
    now = now_epoch()
    total_limit = _parse_limit(query, default=2000)
    rows: List[Dict[str, Any]] = []
    workspaces_scanned = 0
    stale_count = 0
    for collection in collections_svc.list_collections(service, session):
        collection_id = collection.get("_key")
        if not collection_id:
            continue
        config = parse_config_from_collection(collection)
        if not config.get("enabled"):
            continue
        workspaces_scanned += 1
        item_limit = (
            max(1, total_limit - len(rows)) if len(rows) < total_limit else 1
        )
        chunk = list_stale_reviews(
            service,
            collection_id,
            session,
            {"limit": item_limit},
        )
        stale_count += int(chunk.get("stale_count") or 0)
        if len(rows) < total_limit:
            for item in chunk.get("items") or []:
                if len(rows) >= total_limit:
                    break
                enriched = dict(item)
                enriched["collection_name"] = collection.get("name") or ""
                rows.append(enriched)

    truncated = stale_count > len(rows)
    return {
        "generated_at": now,
        "workspaces_scanned": workspaces_scanned,
        "stale_count": stale_count,
        "limit": total_limit,
        "truncated": truncated,
        "items": rows,
        "note": (
            "Includes only workspaces visible to the caller (grant ACL). "
            "Per-workspace detail: GET /stig_collections/{id}/review_aging/stale."
        ),
    }


def _editor_settings_row(service) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    rows = kv_client.query_all(coll)
    return dict(rows[0]) if rows else {}


def is_review_aging_job_enabled(service) -> bool:
    row = _editor_settings_row(service)
    return _as_bool(row.get(JOB_ENABLED_FIELD), False)


def get_review_aging_job(service) -> Dict[str, Any]:
    row = _editor_settings_row(service)
    last_run = parse_json_field(row.get(JOB_LAST_RUN_FIELD), default={}) or {}
    if not isinstance(last_run, dict):
        last_run = {}
    return {
        "enabled": _as_bool(row.get(JOB_ENABLED_FIELD), False),
        "last_run": last_run,
        "defaults": {"enabled": False},
        "note": (
            "When enabled, scheduled search STIG review aging apply runs "
            "enabled per-workspace rules (POST /stig_imports/review_aging_apply). "
            "Destructive deletes require dry_run=false on execute."
        ),
    }


def patch_review_aging_job(
    service, body: Dict[str, Any], username: str
) -> Dict[str, Any]:
    row = _editor_settings_row(service)
    enabled = _as_bool(
        body.get("enabled"),
        _as_bool(row.get(JOB_ENABLED_FIELD), False),
    )
    patch = dict(row)
    patch[JOB_ENABLED_FIELD] = enabled
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    if row.get("_key"):
        stored = kv_client.update_record(coll, row["_key"], kv_record(patch))
    else:
        stored = kv_client.insert_record(coll, kv_record(patch))
    audit.log_event(
        "update",
        "review_aging_job",
        "global",
        username,
        {"enabled": enabled},
    )
    out = get_review_aging_job(service)
    out["settings"] = {
        "enabled": _as_bool(stored.get(JOB_ENABLED_FIELD), False),
        "updated_at": stored.get("updated_at"),
        "updated_by": stored.get("updated_by"),
    }
    return out


def record_review_aging_job_run(
    service, username: str, summary: Dict[str, Any]
) -> None:
    row = _editor_settings_row(service)
    patch = dict(row)
    patch[JOB_LAST_RUN_FIELD] = dumps_json(summary)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username or "review_aging_job"
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    if row.get("_key"):
        kv_client.update_record(coll, row["_key"], kv_record(patch))
    else:
        kv_client.insert_record(coll, kv_record(patch))
