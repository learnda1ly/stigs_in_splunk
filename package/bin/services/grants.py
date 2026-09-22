"""Workspace grant CRUD (users/roles + ACL scope)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import access
import audit
import kv_client
from models import KV_STIG_COLLECTION_GRANTS, dumps_json, kv_record, new_id, now_epoch, parse_json_field
from services import collections as collections_svc

VALID_ROLES = access.GRANT_ROLES


def _grants_coll(service):
    return kv_client.get_collection(service, KV_STIG_COLLECTION_GRANTS)


def query_grants(service, collection_id: str) -> List[Dict[str, Any]]:
    coll = _grants_coll(service)
    return kv_client.query_all(coll, {"stig_collection_id": collection_id})


def query_all_grants_grouped(service) -> Dict[str, List[Dict[str, Any]]]:
    coll = _grants_coll(service)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for rec in kv_client.query_all(coll):
        cid = rec.get("stig_collection_id") or ""
        grouped.setdefault(cid, []).append(rec)
    return grouped


def _require_collection(collection_id: str, session: Dict[str, Any], service) -> Dict[str, Any]:
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    grants = query_grants(service, collection_id)
    if not access.user_can_read_collection(rec, session, grants):
        raise KeyError(collection_id)
    return rec


def _require_manage(collection_id: str, session: Dict[str, Any], service) -> Dict[str, Any]:
    rec = _require_collection(collection_id, session, service)
    grants = query_grants(service, collection_id)
    if not access.user_can_manage_grants(rec, session, grants):
        raise PermissionError("grant management requires owner or manager role")
    return rec


def _normalize_principal(value: Any) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("principal is required (user:<name> or role:<name>)")
    if not (text.startswith("user:") or text.startswith("role:")):
        raise ValueError("principal must start with user: or role:")
    return text


def _normalize_role(value: Any) -> str:
    role = (value or "member").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"grant_role must be one of: {', '.join(sorted(VALID_ROLES))}")
    return role


def _normalize_id_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    parsed = parse_json_field(value, default=[])
    if isinstance(parsed, list):
        return [str(x).strip() for x in parsed if str(x).strip()]
    return []


def _public_grant(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    out["acl_host_ids"] = _normalize_id_list(rec.get("acl_host_ids"))
    out["acl_baseline_ids"] = _normalize_id_list(rec.get("acl_baseline_ids"))
    out["acl_labels"] = _normalize_id_list(rec.get("acl_labels"))
    out["capabilities"] = access.GRANT_CAPABILITIES.get(
        (rec.get("grant_role") or "member").strip().lower(),
        access.GRANT_CAPABILITIES["member"],
    )
    return out


def _sync_access_principal(
    service, collection_id: str, principal: str, add: bool, username: str
) -> None:
    """Keep access_principals in sync for backward-compatible read paths."""
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        return
    principals = access.parse_access_principals(rec.get("access_principals"))
    changed = False
    if add and principal not in principals:
        principals.append(principal)
        changed = True
    if not add and principal in principals:
        principals = [p for p in principals if p != principal]
        changed = True
    if changed:
        collections_svc.update_collection(
            service,
            collection_id,
            {"access_principals": principals},
            username,
        )


def workspace_context(
    service, collection_id: str, session: Dict[str, Any]
) -> tuple[Dict[str, Any], access.WorkspaceAccess, List[Dict[str, Any]]]:
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    grants = query_grants(service, collection_id)
    ctx = access.resolve_workspace_access(rec, session, grants)
    return rec, ctx, grants


def require_workspace_read(
    service, collection_id: str, session: Dict[str, Any]
) -> tuple[Dict[str, Any], access.WorkspaceAccess]:
    rec, ctx, _grants = workspace_context(service, collection_id, session)
    if not ctx.can_read:
        raise PermissionError("access denied to stig_collection")
    return rec, ctx


def require_workspace_write(
    service, collection_id: str, session: Dict[str, Any]
) -> tuple[Dict[str, Any], access.WorkspaceAccess]:
    rec, ctx, _grants = workspace_context(service, collection_id, session)
    if not ctx.can_write:
        raise PermissionError("access denied to stig_collection")
    return rec, ctx


def list_grants(
    service, collection_id: str, session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    _require_collection(collection_id, session, service)
    rows = query_grants(service, collection_id)
    return [_public_grant(r) for r in rows]


def get_grant(
    service, collection_id: str, grant_id: str, session: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    _require_collection(collection_id, session, service)
    coll = _grants_coll(service)
    rec = kv_client.get_by_key(coll, grant_id)
    if not rec or rec.get("stig_collection_id") != collection_id:
        return None
    return _public_grant(rec)


def _find_grant_by_principal(
    service, collection_id: str, principal: str
) -> Optional[Dict[str, Any]]:
    for rec in query_grants(service, collection_id):
        if (rec.get("principal") or "").strip() == principal:
            return rec
    return None


def create_grant(
    service,
    collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_manage(collection_id, session, service)
    principal = _normalize_principal(body.get("principal"))
    role = _normalize_role(body.get("grant_role"))
    existing = _find_grant_by_principal(service, collection_id, principal)
    if existing:
        raise ValueError("a grant for this principal already exists")
    key = new_id()
    ts = now_epoch()
    record = kv_record(
        {
            "_key": key,
            "stig_collection_id": collection_id,
            "principal": principal,
            "grant_role": role,
            "acl_host_ids": dumps_json(_normalize_id_list(body.get("acl_host_ids"))),
            "acl_baseline_ids": dumps_json(
                _normalize_id_list(body.get("acl_baseline_ids"))
            ),
            "acl_labels": dumps_json(
                _normalize_id_list(
                    body.get("acl_labels") if "acl_labels" in body else body.get("acl_label_ids")
                )
            ),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    coll = _grants_coll(service)
    stored = kv_client.insert_record(coll, record)
    _sync_access_principal(service, collection_id, principal, add=True, username=username)
    audit.log_event(
        "create",
        "stig_collection_grant",
        key,
        username,
        {"stig_collection_id": collection_id, "principal": principal, "grant_role": role},
    )
    return _public_grant(stored)


def update_grant(
    service,
    collection_id: str,
    grant_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_manage(collection_id, session, service)
    coll = _grants_coll(service)
    existing = kv_client.get_by_key(coll, grant_id)
    if not existing or existing.get("stig_collection_id") != collection_id:
        raise KeyError(grant_id)
    patch = dict(existing)
    old_principal = (existing.get("principal") or "").strip()
    if "principal" in body:
        new_principal = _normalize_principal(body.get("principal"))
        if new_principal != old_principal:
            clash = _find_grant_by_principal(service, collection_id, new_principal)
            if clash and clash.get("_key") != grant_id:
                raise ValueError("a grant for this principal already exists")
            patch["principal"] = new_principal
    if "grant_role" in body:
        patch["grant_role"] = _normalize_role(body.get("grant_role"))
    if "acl_host_ids" in body:
        patch["acl_host_ids"] = dumps_json(_normalize_id_list(body.get("acl_host_ids")))
    if "acl_baseline_ids" in body:
        patch["acl_baseline_ids"] = dumps_json(
            _normalize_id_list(body.get("acl_baseline_ids"))
        )
    if "acl_labels" in body or "acl_label_ids" in body:
        patch["acl_labels"] = dumps_json(
            _normalize_id_list(body.get("acl_labels") or body.get("acl_label_ids"))
        )
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, grant_id, kv_record(patch))
    new_principal = (stored.get("principal") or "").strip()
    if new_principal != old_principal:
        _sync_access_principal(
            service, collection_id, old_principal, add=False, username=username
        )
        _sync_access_principal(
            service, collection_id, new_principal, add=True, username=username
        )
    audit.log_event("update", "stig_collection_grant", grant_id, username, body)
    return _public_grant(stored)


def update_grant_acl(
    service,
    collection_id: str,
    grant_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    patch = {}
    if "acl_host_ids" in body:
        patch["acl_host_ids"] = body.get("acl_host_ids")
    if "acl_baseline_ids" in body:
        patch["acl_baseline_ids"] = body.get("acl_baseline_ids")
    if "acl_labels" in body:
        patch["acl_labels"] = body.get("acl_labels")
    if "acl_label_ids" in body:
        patch["acl_labels"] = body.get("acl_label_ids")
    if not patch:
        raise ValueError("acl_host_ids, acl_baseline_ids, and/or acl_labels required")
    return update_grant(service, collection_id, grant_id, patch, username, session)


def delete_grant(
    service,
    collection_id: str,
    grant_id: str,
    username: str,
    session: Dict[str, Any],
) -> None:
    _require_manage(collection_id, session, service)
    coll = _grants_coll(service)
    existing = kv_client.get_by_key(coll, grant_id)
    if not existing or existing.get("stig_collection_id") != collection_id:
        raise KeyError(grant_id)
    principal = (existing.get("principal") or "").strip()
    kv_client.delete_record(coll, grant_id)
    _sync_access_principal(service, collection_id, principal, add=False, username=username)
    audit.log_event("delete", "stig_collection_grant", grant_id, username)
