"""Optional arbitrary JSON metadata on stig_collections (workspace settings)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import audit
import kv_client
from models import KV_STIG_COLLECTIONS, dumps_json, kv_record, now_epoch, parse_json_field
from services import collections as collections_svc

METADATA_FIELD = "metadata"


def empty_metadata() -> Dict[str, Any]:
    return {}


def parse_metadata_from_collection(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = parse_json_field((rec or {}).get(METADATA_FIELD), default={})
    if raw is None:
        return empty_metadata()
    if not isinstance(raw, dict):
        raise ValueError("stored metadata must be a JSON object")
    return dict(raw)


def normalize_metadata(value: Any) -> Dict[str, Any]:
    if value is None:
        return empty_metadata()
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    out: Dict[str, Any] = {}
    for key, val in value.items():
        key_str = str(key)
        if not key_str:
            raise ValueError("metadata keys must be non-empty strings")
        try:
            dumps_json(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metadata value for {key_str!r} is not JSON-serializable") from exc
        out[key_str] = val
    return out


def merge_metadata(
    existing: Dict[str, Any], patch: Dict[str, Any], *, replace: bool = False
) -> Dict[str, Any]:
    base = {} if replace else dict(existing)
    for key, val in patch.items():
        if val is None:
            base.pop(key, None)
        else:
            base[key] = val
    return normalize_metadata(base)


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


def get_metadata(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    rec = _require_read(service, collection_id, session)
    metadata = parse_metadata_from_collection(rec)
    return {
        "stig_collection_id": collection_id,
        "metadata": metadata,
    }


def patch_metadata(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)

    if body.get("clear") is True:
        metadata = empty_metadata()
    else:
        incoming = body.get("metadata")
        if incoming is None and "metadata" not in body and not body.get("clear"):
            raise ValueError("metadata object is required (or clear: true)")
        replace = bool(body.get("replace"))
        if incoming is None and body.get("clear") is not True:
            incoming = {}
        existing = parse_metadata_from_collection(rec)
        metadata = merge_metadata(existing, normalize_metadata(incoming), replace=replace)

    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    patch = dict(rec)
    patch[METADATA_FIELD] = dumps_json(metadata)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, collection_id, kv_record(patch))
    audit.log_event(
        "update",
        "stig_collection_metadata",
        collection_id,
        username,
        {"metadata_keys": sorted(metadata.keys())},
    )
    return {
        "stig_collection_id": collection_id,
        "metadata": metadata,
        "collection": stored,
    }
