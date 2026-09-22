"""stig_hosts CRUD."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import access
import audit
import kv_client
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_HOSTS,
    dumps_json,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)
from services import collections as collections_svc
from services import grants as grants_svc
from services import labels as labels_svc


def _require_collection_access(service, collection_id: str, session: Dict[str, Any], write: bool = False):
    try:
        _rec, ctx = (
            grants_svc.require_workspace_write(service, collection_id, session)
            if write
            else grants_svc.require_workspace_read(service, collection_id, session)
        )
    except KeyError as exc:
        raise KeyError(collection_id) from exc


def _access_context(service, collection_id: str, session: Dict[str, Any]):
    _rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    return ctx


def _normalize_label_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    parsed = parse_json_field(value, default=[])
    if isinstance(parsed, list):
        return [str(x).strip() for x in parsed if str(x).strip()]
    return []


def _public_host(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    out["label_ids"] = _normalize_label_ids(rec.get("label_ids"))
    return out


def list_hosts(
    service,
    session: Dict[str, Any],
    stig_collection_id: Optional[str] = None,
    label_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    query = {"stig_collection_id": stig_collection_id} if stig_collection_id else {}
    records = kv_client.query_all(coll, query)
    if stig_collection_id:
        _require_collection_access(service, stig_collection_id, session)
        ctx = _access_context(service, stig_collection_id, session)
        records = access.filter_hosts(records, ctx)
        if label_id:
            records = [
                r
                for r in records
                if label_id in _normalize_label_ids(r.get("label_ids"))
            ]
        return [_public_host(r) for r in records]
    visible = collections_svc.list_collections(service, session)
    by_id = {r["_key"]: r for r in visible}
    out: List[Dict[str, Any]] = []
    for rec in records:
        cid = rec.get("stig_collection_id")
        if cid not in by_id:
            continue
        ctx = _access_context(service, cid, session)
        if access.host_allowed(rec, ctx):
            if label_id and label_id not in _normalize_label_ids(rec.get("label_ids")):
                continue
            out.append(_public_host(rec))
    return out


def find_host_by_hostname(
    service,
    session: Dict[str, Any],
    stig_collection_id: str,
    hostname: str,
) -> Optional[Dict[str, Any]]:
    want = (hostname or "").strip().casefold()
    if not want:
        return None
    for rec in list_hosts(service, session, stig_collection_id):
        if (rec.get("hostname") or "").strip().casefold() == want:
            return rec
    return None


def get_host(service, key: str, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    rec = kv_client.get_by_key(coll, key)
    if not rec:
        return None
    try:
        _require_collection_access(service, rec["stig_collection_id"], session)
    except (KeyError, PermissionError):
        return None
    ctx = _access_context(service, rec["stig_collection_id"], session)
    if not access.host_allowed(rec, ctx):
        return None
    return _public_host(rec)


def create_host(service, body: Dict[str, Any], username: str, session: Dict[str, Any]) -> Dict[str, Any]:
    collection_id = body.get("stig_collection_id")
    if not collection_id:
        raise ValueError("stig_collection_id required")
    _require_collection_access(service, collection_id, session, write=True)

    label_ids = _normalize_label_ids(body.get("label_ids"))
    labels_svc.validate_label_ids(service, collection_id, label_ids)

    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    key = new_id()
    ts = now_epoch()
    metadata = body.get("metadata")
    record = kv_record(
        {
            "_key": key,
            "stig_collection_id": collection_id,
            "hostname": body.get("hostname") or "",
            "ip_address": body.get("ip_address") or "",
            "fqdn": body.get("fqdn") or "",
            "mac_address": body.get("mac_address") or "",
            "role": body.get("role") or "None",
            "asset_type": body.get("asset_type") or "Computing",
            "tech_area": body.get("tech_area") or "",
            "web_or_database": bool(body.get("web_or_database", False)),
            "metadata": dumps_json(metadata) if isinstance(metadata, dict) else (metadata or "{}"),
            "label_ids": dumps_json(label_ids),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored = kv_client.insert_record(coll, record)
    audit.log_event("create", "stig_host", key, username, {"stig_collection_id": collection_id})
    return _public_host(stored)


def _move_host_checklists(
    service,
    host_key: str,
    dest_collection: str,
    username: str,
    updated_at: int,
) -> int:
    cl_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    moved = 0
    for rec in kv_client.query_all(cl_coll, {"host_id": host_key}):
        cl_patch = dict(rec)
        cl_patch["stig_collection_id"] = dest_collection
        cl_patch["updated_at"] = updated_at
        cl_patch["updated_by"] = username
        kv_client.update_record(cl_coll, rec["_key"], kv_record(cl_patch))
        moved += 1
    return moved


def transfer_host_to_collection(
    service,
    host_key: str,
    source_collection_id: str,
    dest_collection_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """Move one host and its checklists; enforce source membership and write ACL."""
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    existing = kv_client.get_by_key(coll, host_key)
    if not existing:
        raise KeyError(host_key)
    current = existing.get("stig_collection_id") or ""
    if current != source_collection_id:
        raise ValueError("host_not_in_source_workspace")
    if dest_collection_id == current:
        return {
            **_public_host(existing),
            "checklists_moved": 0,
        }
    _require_collection_access(service, current, session, write=True)
    _require_collection_access(service, dest_collection_id, session, write=True)

    patch = dict(existing)
    patch["stig_collection_id"] = dest_collection_id
    sanitized = labels_svc.sanitize_label_ids_for_workspace(
        service,
        dest_collection_id,
        _normalize_label_ids(patch.get("label_ids")),
    )
    patch["label_ids"] = dumps_json(sanitized)
    ts = now_epoch()
    patch["updated_at"] = ts
    patch["updated_by"] = username
    checklists_moved = _move_host_checklists(
        service, host_key, dest_collection_id, username, ts
    )
    stored = kv_client.update_record(coll, host_key, kv_record(patch))
    audit.log_event(
        "transfer",
        "stig_host",
        host_key,
        username,
        {
            "from_stig_collection_id": current,
            "to_stig_collection_id": dest_collection_id,
            "hostname": stored.get("hostname"),
            "checklists_moved": checklists_moved,
            "label_ids": _normalize_label_ids(stored.get("label_ids")),
        },
    )
    out = _public_host(stored)
    out["checklists_moved"] = checklists_moved
    return out


def update_host(
    service, key: str, body: Dict[str, Any], username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection_access(service, existing["stig_collection_id"], session, write=True)

    dest_collection = body.get("stig_collection_id")
    moving = bool(
        dest_collection and dest_collection != existing.get("stig_collection_id")
    )
    if moving:
        moved = transfer_host_to_collection(
            service,
            key,
            existing.get("stig_collection_id") or "",
            dest_collection,
            username,
            session,
        )
        patch = dict(existing)
        for field in (
            "hostname",
            "ip_address",
            "fqdn",
            "mac_address",
            "role",
            "asset_type",
            "tech_area",
            "web_or_database",
        ):
            if field in body:
                patch[field] = body[field]
        if "metadata" in body:
            val = body["metadata"]
            patch["metadata"] = dumps_json(val) if isinstance(val, dict) else val
        if "label_ids" in body:
            label_ids = _normalize_label_ids(body.get("label_ids"))
            labels_svc.validate_label_ids(service, dest_collection, label_ids)
            patch["label_ids"] = dumps_json(label_ids)
            patch["updated_at"] = now_epoch()
            patch["updated_by"] = username
            stored = kv_client.update_record(coll, key, kv_record(patch))
            audit.log_event("update", "stig_host", key, username, body)
            return _public_host(stored)
        if any(
            field in body
            for field in (
                "hostname",
                "ip_address",
                "fqdn",
                "mac_address",
                "role",
                "asset_type",
                "tech_area",
                "web_or_database",
                "metadata",
            )
        ):
            patch["updated_at"] = now_epoch()
            patch["updated_by"] = username
            stored = kv_client.update_record(coll, key, kv_record(patch))
            audit.log_event("update", "stig_host", key, username, body)
            return _public_host(stored)
        return _public_host(moved)

    patch = dict(existing)
    workspace_for_labels = existing.get("stig_collection_id") or ""
    for field in (
        "hostname",
        "ip_address",
        "fqdn",
        "mac_address",
        "role",
        "asset_type",
        "tech_area",
        "web_or_database",
    ):
        if field in body:
            patch[field] = body[field]
    if "metadata" in body:
        val = body["metadata"]
        patch["metadata"] = dumps_json(val) if isinstance(val, dict) else val
    if "label_ids" in body:
        label_ids = _normalize_label_ids(body.get("label_ids"))
        labels_svc.validate_label_ids(service, workspace_for_labels, label_ids)
        patch["label_ids"] = dumps_json(label_ids)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_host", key, username, body)
    return _public_host(stored)


def delete_host(service, key: str, username: str, session: Dict[str, Any]) -> None:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection_access(service, existing["stig_collection_id"], session, write=True)
    kv_client.delete_record(coll, key)
    audit.log_event("delete", "stig_host", key, username)
