"""Per-workspace review validation policy (collection settings)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import audit
import kv_client
import validation
from models import KV_STIG_COLLECTIONS, dumps_json, kv_record, now_epoch, parse_json_field
from services import collections as collections_svc

REVIEW_REQUIREMENTS_FIELD = "review_requirements"

POLICY_FIELD_NAMES = tuple(validation.DEFAULT_POLICY.keys())

ALLOWED_STATUSES = frozenset(
    {"not_reviewed", "open", "not_a_finding", "not_applicable"}
)


def default_policy() -> Dict[str, Any]:
    return validation.default_policy()


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


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"expected integer, got {value!r}")
    if parsed < 0:
        raise ValueError("length minimums must be >= 0")
    return parsed


def normalize_policy(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge stored policy with defaults; validate shape."""
    src = raw if isinstance(raw, dict) else {}
    out = default_policy()
    out["require_finding_details"] = _as_bool(
        src.get("require_finding_details"), out["require_finding_details"]
    )
    out["require_comments"] = _as_bool(
        src.get("require_comments"), out["require_comments"]
    )
    out["min_finding_details_length"] = _as_int(
        src.get("min_finding_details_length"), out["min_finding_details_length"]
    )
    out["min_comments_length"] = _as_int(
        src.get("min_comments_length"), out["min_comments_length"]
    )
    statuses = src.get("applies_to_statuses")
    if statuses is None:
        statuses = []
    if not isinstance(statuses, list):
        raise ValueError("applies_to_statuses must be an array")
    normalized: List[str] = []
    for item in statuses:
        key = str(item or "").strip().lower()
        if not key:
            continue
        if key not in ALLOWED_STATUSES:
            raise ValueError(f"invalid status in applies_to_statuses: {item}")
        if key not in normalized:
            normalized.append(key)
    out["applies_to_statuses"] = normalized
    if out["min_finding_details_length"] > 0:
        out["require_finding_details"] = True
    if out["min_comments_length"] > 0:
        out["require_comments"] = True
    return out


def parse_policy_from_collection(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = parse_json_field((rec or {}).get(REVIEW_REQUIREMENTS_FIELD), default={}) or {}
    if not isinstance(raw, dict):
        return default_policy()
    return normalize_policy(raw)


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


def get_policy(
    service, collection_id: str, session: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    if session is not None:
        rec = _require_read(service, collection_id, session)
    else:
        rec = collections_svc.get_collection(service, collection_id)
        if not rec:
            raise KeyError(collection_id)
    return parse_policy_from_collection(rec)


def get_requirements(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    rec = _require_read(service, collection_id, session)
    policy = parse_policy_from_collection(rec)
    return {
        "stig_collection_id": collection_id,
        "review_requirements": policy,
        "defaults": default_policy(),
    }


def patch_requirements(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    incoming = body.get("review_requirements")
    if incoming is None and any(k in body for k in POLICY_FIELD_NAMES):
        incoming = body
    if not isinstance(incoming, dict):
        raise ValueError("review_requirements object is required")
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
    patch[REVIEW_REQUIREMENTS_FIELD] = dumps_json(policy)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, collection_id, kv_record(patch))
    audit.log_event(
        "update",
        "stig_collection_review_requirements",
        collection_id,
        username,
        {"review_requirements": policy},
    )
    return {
        "stig_collection_id": collection_id,
        "review_requirements": policy,
        "collection": stored,
    }
