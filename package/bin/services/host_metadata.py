"""Optional arbitrary JSON metadata on stig_hosts (asset records)."""

from __future__ import annotations

from typing import Any, Dict

import access
import audit
import kv_client
from models import KV_STIG_HOSTS, dumps_json, kv_record, now_epoch
from services import grants as grants_svc
from services.collection_metadata import (
    METADATA_FIELD,
    empty_metadata,
    merge_metadata,
    normalize_metadata,
    parse_metadata_from_collection,
)


def _host_with_acl(
    service, host_id: str, session: Dict[str, Any], *, write: bool = False
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    rec = kv_client.get_by_key(coll, host_id)
    if not rec:
        raise KeyError(host_id)
    collection_id = rec.get("stig_collection_id") or ""
    try:
        if write:
            grants_svc.require_workspace_write(service, collection_id, session)
        else:
            grants_svc.require_workspace_read(service, collection_id, session)
    except KeyError as exc:
        raise KeyError(host_id) from exc
    except PermissionError as exc:
        if write:
            raise
        raise KeyError(host_id) from exc
    _rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not access.host_allowed(rec, ctx):
        raise KeyError(host_id)
    return rec


def get_metadata(
    service, host_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    rec = _host_with_acl(service, host_id, session, write=False)
    metadata = parse_metadata_from_collection(rec)
    return {
        "stig_host_id": host_id,
        "metadata": metadata,
    }


def patch_metadata(
    service,
    host_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    rec = _host_with_acl(service, host_id, session, write=True)

    if body.get("clear") is True:
        metadata = empty_metadata()
    else:
        if "metadata" in body and body.get("metadata") is None:
            raise ValueError("metadata must be a JSON object")
        incoming = body.get("metadata")
        if incoming is None:
            raise ValueError("metadata object is required (or clear: true)")
        replace = bool(body.get("replace"))
        existing = parse_metadata_from_collection(rec)
        metadata = merge_metadata(existing, normalize_metadata(incoming), replace=replace)

    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    patch = dict(rec)
    patch[METADATA_FIELD] = dumps_json(metadata)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, host_id, kv_record(patch))
    audit.log_event(
        "update",
        "stig_host_metadata",
        host_id,
        username,
        {
            "stig_collection_id": rec.get("stig_collection_id"),
            "metadata_keys": sorted(metadata.keys()),
        },
    )
    return {
        "stig_host_id": host_id,
        "metadata": metadata,
        "host": stored,
    }
