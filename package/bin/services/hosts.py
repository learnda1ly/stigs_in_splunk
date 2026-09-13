"""stig_hosts CRUD."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import access
import audit
import kv_client
from models import KV_STIG_HOSTS, dumps_json, kv_record, new_id, now_epoch
from services import collections as collections_svc


def _require_collection_access(service, collection_id: str, session: Dict[str, Any], write: bool = False):
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    ok = access.user_can_write_collection(rec, session) if write else access.user_can_read_collection(rec, session)
    if not ok:
        raise PermissionError("access denied to stig_collection")


def list_hosts(
    service, session: Dict[str, Any], stig_collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    query = {"stig_collection_id": stig_collection_id} if stig_collection_id else {}
    records = kv_client.query_all(coll, query)
    if stig_collection_id:
        _require_collection_access(service, stig_collection_id, session)
        return records
    allowed = {r["_key"] for r in collections_svc.list_collections(service, session)}
    collection_ids = allowed
    return [r for r in records if r.get("stig_collection_id") in collection_ids]


def get_host(service, key: str, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    rec = kv_client.get_by_key(coll, key)
    if rec:
        _require_collection_access(service, rec["stig_collection_id"], session)
    return rec


def create_host(service, body: Dict[str, Any], username: str, session: Dict[str, Any]) -> Dict[str, Any]:
    collection_id = body.get("stig_collection_id")
    if not collection_id:
        raise ValueError("stig_collection_id required")
    _require_collection_access(service, collection_id, session, write=True)

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
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored = kv_client.insert_record(coll, record)
    audit.log_event("create", "stig_host", key, username, {"stig_collection_id": collection_id})
    return stored


def update_host(
    service, key: str, body: Dict[str, Any], username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection_access(service, existing["stig_collection_id"], session, write=True)

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
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_host", key, username, body)
    return stored


def delete_host(service, key: str, username: str, session: Dict[str, Any]) -> None:
    coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection_access(service, existing["stig_collection_id"], session, write=True)
    kv_client.delete_record(coll, key)
    audit.log_event("delete", "stig_host", key, username)
