"""stig_collections CRUD."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import access
import audit
import kv_client
from models import (
    KV_STIG_COLLECTIONS,
    dumps_json,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)


def list_collections(service, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    records = kv_client.query_all(coll)
    return access.filter_collections_for_user(records, session)


def get_collection(service, key: str) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    return kv_client.get_by_key(coll, key)


def create_collection(
    service, body: Dict[str, Any], username: str
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    key = new_id()
    ts = now_epoch()
    principals = body.get("access_principals")
    if isinstance(principals, list):
        principals_str = dumps_json(principals)
    else:
        principals_str = principals or dumps_json([f"user:{username}"])
    record = kv_record(
        {
            "_key": key,
            "name": body.get("name") or "Untitled",
            "description": body.get("description") or "",
            "access_principals": principals_str,
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored = kv_client.insert_record(coll, record)
    audit.log_event("create", "stig_collection", key, username, {"name": stored.get("name")})
    return stored


def update_collection(
    service, key: str, body: Dict[str, Any], username: str
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    patch = dict(existing)
    if "name" in body:
        patch["name"] = body["name"]
    if "description" in body:
        patch["description"] = body["description"]
    if "access_principals" in body:
        val = body["access_principals"]
        patch["access_principals"] = dumps_json(val) if isinstance(val, list) else val
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_collection", key, username, body)
    return stored


def delete_collection(service, key: str, username: str) -> None:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    if not kv_client.get_by_key(coll, key):
        raise KeyError(key)
    kv_client.delete_record(coll, key)
    audit.log_event("delete", "stig_collection", key, username)
