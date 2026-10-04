"""Per-workspace checklist import policy (STIG Manager collection import options)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import audit
import kv_client
from models import KV_STIG_COLLECTIONS, dumps_json, kv_record, now_epoch, parse_json_field
from services import collections as collections_svc

IMPORT_OPTIONS_FIELD = "import_options"

STATUS_PER_RESULT_VALUES = frozenset(
    {"keep_existing", "saved", "submitted", "accepted"}
)
INCLUDE_UNREVIEWED_VALUES = frozenset({"never", "with_comments", "always"})
UNREVIEWED_WITH_COMMENT_VALUES = frozenset({"informational", "not_reviewed"})
EMPTY_TEXT_VALUES = frozenset({"ignored", "replaced", "imported"})

POLICY_FIELD_NAMES = (
    "status_per_result",
    "include_unreviewed",
    "unreviewed_with_comment",
    "empty_detail",
    "empty_comment",
    "allow_customize_per_import",
    "lock_automation_import_options",
)


def default_policy() -> Dict[str, Any]:
    return {
        "status_per_result": {
            "fail": "saved",
            "pass": "saved",
            "notapplicable": "saved",
        },
        "include_unreviewed": "with_comments",
        "unreviewed_with_comment": "informational",
        "empty_detail": "ignored",
        "empty_comment": "ignored",
        "allow_customize_per_import": True,
        "lock_automation_import_options": False,
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


def _normalize_status_per_result(raw: Any, defaults: Dict[str, str]) -> Dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    out = dict(defaults)
    for key in ("fail", "pass", "notapplicable"):
        if key not in src:
            continue
        val = str(src.get(key) or "").strip().lower()
        if val not in STATUS_PER_RESULT_VALUES:
            raise ValueError(
                f"status_per_result.{key} must be one of "
                + ", ".join(sorted(STATUS_PER_RESULT_VALUES))
            )
        out[key] = val
    return out


def normalize_policy(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    defaults = default_policy()
    out = default_policy()
    out["status_per_result"] = _normalize_status_per_result(
        src.get("status_per_result"), defaults["status_per_result"]
    )
    include = str(src.get("include_unreviewed") or defaults["include_unreviewed"]).strip().lower()
    if include not in INCLUDE_UNREVIEWED_VALUES:
        raise ValueError("include_unreviewed must be never, with_comments, or always")
    out["include_unreviewed"] = include
    unrev = str(
        src.get("unreviewed_with_comment") or defaults["unreviewed_with_comment"]
    ).strip().lower()
    if unrev not in UNREVIEWED_WITH_COMMENT_VALUES:
        raise ValueError("unreviewed_with_comment must be informational or not_reviewed")
    out["unreviewed_with_comment"] = unrev
    for field in ("empty_detail", "empty_comment"):
        val = str(src.get(field) or defaults[field]).strip().lower()
        if val not in EMPTY_TEXT_VALUES:
            raise ValueError(f"{field} must be ignored, replaced, or imported")
        out[field] = val
    out["allow_customize_per_import"] = _as_bool(
        src.get("allow_customize_per_import"), defaults["allow_customize_per_import"]
    )
    out["lock_automation_import_options"] = _as_bool(
        src.get("lock_automation_import_options"),
        defaults["lock_automation_import_options"],
    )
    return out


def parse_policy_from_collection(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = parse_json_field((rec or {}).get(IMPORT_OPTIONS_FIELD), default={}) or {}
    if not isinstance(raw, dict):
        return default_policy()
    return normalize_policy(raw)


def merge_policy(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not override or not isinstance(override, dict):
        return normalize_policy(base)
    merged = dict(base)
    for key in POLICY_FIELD_NAMES:
        if key in override:
            merged[key] = override[key]
    return normalize_policy(merged)


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


def effective_policy(
    service,
    collection_id: str,
    session: Optional[Dict[str, Any]],
    *,
    override: Optional[Dict[str, Any]] = None,
    automation: bool = False,
) -> Dict[str, Any]:
    """Resolve policy for an ingest path (UI import vs HEC/reconcile automation)."""
    base = get_policy(service, collection_id, session)
    if automation and base.get("lock_automation_import_options"):
        return base
    if automation:
        return base
    if override and base.get("allow_customize_per_import"):
        return merge_policy(base, override)
    return base


def get_options(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    rec = _require_read(service, collection_id, session)
    policy = parse_policy_from_collection(rec)
    return {
        "stig_collection_id": collection_id,
        "import_options": policy,
        "defaults": default_policy(),
    }


def patch_options(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    incoming = body.get("import_options")
    if incoming is None and any(k in body for k in POLICY_FIELD_NAMES):
        incoming = body
    if not isinstance(incoming, dict):
        raise ValueError("import_options object is required")
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
    patch[IMPORT_OPTIONS_FIELD] = dumps_json(policy)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, collection_id, kv_record(patch))
    audit.log_event(
        "update",
        "stig_collection_import_options",
        collection_id,
        username,
        {"import_options": policy},
    )
    return {
        "stig_collection_id": collection_id,
        "import_options": policy,
        "collection": stored,
    }
