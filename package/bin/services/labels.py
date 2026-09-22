"""Workspace-scoped asset labels (for grants ACL and host filtering)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import audit
import kv_client
from models import KV_STIG_HOSTS, KV_STIG_LABELS, dumps_json, kv_record, new_id, now_epoch, parse_json_field
from services import grants as grants_svc


def _labels_coll(service):
    return kv_client.get_collection(service, KV_STIG_LABELS)


def _normalize_label_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    parsed = parse_json_field(value, default=[])
    if isinstance(parsed, list):
        return [str(x).strip() for x in parsed if str(x).strip()]
    return []


def _public_label(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    return out


def _require_read(collection_id: str, session: Dict[str, Any], service) -> None:
    grants_svc.require_workspace_read(service, collection_id, session)


def _require_write(collection_id: str, session: Dict[str, Any], service) -> None:
    grants_svc.require_workspace_write(service, collection_id, session)


def list_labels(
    service, collection_id: str, session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    _require_read(collection_id, session, service)
    coll = _labels_coll(service)
    rows = kv_client.query_all(coll, {"stig_collection_id": collection_id})
    return [_public_label(r) for r in rows]


def get_label(
    service, collection_id: str, label_id: str, session: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    _require_read(collection_id, session, service)
    coll = _labels_coll(service)
    rec = kv_client.get_by_key(coll, label_id)
    if not rec or rec.get("stig_collection_id") != collection_id:
        return None
    return _public_label(rec)


def create_label(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(collection_id, session, service)
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    key = new_id()
    ts = now_epoch()
    record = kv_record(
        {
            "_key": key,
            "stig_collection_id": collection_id,
            "name": name,
            "color": (body.get("color") or "").strip(),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    coll = _labels_coll(service)
    stored = kv_client.insert_record(coll, record)
    audit.log_event(
        "create",
        "stig_label",
        key,
        username,
        {"stig_collection_id": collection_id, "name": name},
    )
    return _public_label(stored)


def update_label(
    service,
    collection_id: str,
    label_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(collection_id, session, service)
    coll = _labels_coll(service)
    existing = kv_client.get_by_key(coll, label_id)
    if not existing or existing.get("stig_collection_id") != collection_id:
        raise KeyError(label_id)
    patch = dict(existing)
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        patch["name"] = name
    if "color" in body:
        patch["color"] = (body.get("color") or "").strip()
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, label_id, kv_record(patch))
    audit.log_event("update", "stig_label", label_id, username, body)
    return _public_label(stored)


def delete_label(
    service,
    collection_id: str,
    label_id: str,
    username: str,
    session: Dict[str, Any],
) -> None:
    _require_write(collection_id, session, service)
    coll = _labels_coll(service)
    existing = kv_client.get_by_key(coll, label_id)
    if not existing or existing.get("stig_collection_id") != collection_id:
        raise KeyError(label_id)
    kv_client.delete_record(coll, label_id)
    hosts_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    ts = now_epoch()
    for host in kv_client.query_all(hosts_coll, {"stig_collection_id": collection_id}):
        ids = _normalize_label_ids(host.get("label_ids"))
        if label_id not in ids:
            continue
        patch = dict(host)
        patch["label_ids"] = dumps_json([x for x in ids if x != label_id])
        patch["updated_at"] = ts
        patch["updated_by"] = username
        kv_client.update_record(hosts_coll, host["_key"], kv_record(patch))
    audit.log_event("delete", "stig_label", label_id, username)


def assign_label_to_hosts(
    service,
    collection_id: str,
    label_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """Add label to host ids (idempotent)."""
    _require_write(collection_id, session, service)
    if not get_label(service, collection_id, label_id, session):
        raise KeyError(label_id)
    host_ids = _normalize_label_ids(body.get("host_ids"))
    if not host_ids:
        raise ValueError("host_ids required")
    hosts_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    ts = now_epoch()
    updated = 0
    for host_key in host_ids:
        host = kv_client.get_by_key(hosts_coll, host_key)
        if not host or host.get("stig_collection_id") != collection_id:
            continue
        ids = _normalize_label_ids(host.get("label_ids"))
        if label_id in ids:
            continue
        ids.append(label_id)
        patch = dict(host)
        patch["label_ids"] = dumps_json(ids)
        patch["updated_at"] = ts
        patch["updated_by"] = username
        kv_client.update_record(hosts_coll, host_key, kv_record(patch))
        updated += 1
    return {"label_id": label_id, "updated_hosts": updated}
