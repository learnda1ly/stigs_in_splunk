"""Per-workspace review history retention (STIG Manager collection settings §2.9.1.4.3)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import audit
import kv_client
from models import KV_STIG_COLLECTIONS, dumps_json, kv_record, now_epoch, parse_json_field
from services import collections as collections_svc

REVIEW_HISTORY_CONFIG_FIELD = "review_history_config"

DEFAULT_MAX_RECORDS_PER_REVIEW = 15
MAX_RECORDS_PER_REVIEW_CAP = 15

POLICY_FIELD_NAMES = (
    "enabled",
    "max_records_per_review",
)


def default_policy() -> Dict[str, Any]:
    return {
        "enabled": True,
        "max_records_per_review": DEFAULT_MAX_RECORDS_PER_REVIEW,
    }


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_policy(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out = default_policy()
    out["enabled"] = _as_bool(src.get("enabled"), out["enabled"])
    raw_max = src.get("max_records_per_review")
    if raw_max is None or raw_max == "":
        max_val = out["max_records_per_review"]
    else:
        try:
            max_val = int(raw_max)
        except (TypeError, ValueError):
            raise ValueError("max_records_per_review must be an integer")
        if max_val < 0:
            raise ValueError("max_records_per_review must be >= 0")
        if out["enabled"] and max_val > MAX_RECORDS_PER_REVIEW_CAP:
            raise ValueError(
                f"max_records_per_review cannot exceed {MAX_RECORDS_PER_REVIEW_CAP}"
            )
    out["max_records_per_review"] = max_val
    if not out["enabled"]:
        return out
    if out["max_records_per_review"] < 1:
        raise ValueError(
            "max_records_per_review must be at least 1 when review history is enabled"
        )
    return out


def parse_policy_from_collection(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = parse_json_field((rec or {}).get(REVIEW_HISTORY_CONFIG_FIELD), default={}) or {}
    if not isinstance(raw, dict):
        return default_policy()
    return normalize_policy(raw)


def policy_for_collection_id(service, collection_id: str) -> Dict[str, Any]:
    if not collection_id:
        return default_policy()
    rec = collections_svc.get_collection(service, collection_id)
    return parse_policy_from_collection(rec)


def _require_write(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    from services import grants as grants_svc

    rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not ctx.can_write:
        raise PermissionError("access denied to stig_collection")
    return rec


def _require_read(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    from services import grants as grants_svc

    rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not ctx.can_read:
        raise KeyError(collection_id)
    return rec


def get_config(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    rec = _require_read(service, collection_id, session)
    policy = parse_policy_from_collection(rec)
    return {
        "stig_collection_id": collection_id,
        "review_history_config": policy,
        "defaults": default_policy(),
        "limits": {
            "max_records_per_review_cap": MAX_RECORDS_PER_REVIEW_CAP,
        },
    }


def patch_config(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    incoming = body.get("review_history_config")
    if incoming is None and any(k in body for k in POLICY_FIELD_NAMES):
        incoming = body
    if not isinstance(incoming, dict):
        raise ValueError("review_history_config object is required")
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    merged = parse_policy_from_collection(rec)
    for key in POLICY_FIELD_NAMES:
        if key in incoming:
            merged[key] = incoming[key]
    policy = normalize_policy(merged)
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    patch = dict(rec)
    patch[REVIEW_HISTORY_CONFIG_FIELD] = dumps_json(policy)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, collection_id, kv_record(patch))
    audit.log_event(
        "update",
        "stig_collection_review_history_config",
        collection_id,
        username,
        {"review_history_config": policy},
    )
    return {
        "stig_collection_id": collection_id,
        "review_history_config": policy,
        "collection": stored,
    }


def apply_retention_to_rows(
    rows: List[Dict[str, Any]],
    policy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Keep only the newest retained rows per review (read-time cap)."""
    if not policy.get("enabled"):
        return []
    cap = int(policy.get("max_records_per_review") or DEFAULT_MAX_RECORDS_PER_REVIEW)
    if cap <= 0:
        return []
    by_review: Dict[str, List[Dict[str, Any]]] = {}
    for rec in rows:
        rid = str(rec.get("review_id") or "")
        by_review.setdefault(rid, []).append(rec)
    kept: List[Dict[str, Any]] = []
    for group in by_review.values():
        group.sort(key=lambda r: float(r.get("created_at") or 0), reverse=True)
        kept.extend(group[:cap])
    return kept
