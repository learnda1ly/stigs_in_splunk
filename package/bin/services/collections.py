"""stig_collections CRUD."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import access
import audit
import kv_client
from models import (
    KV_STIG_ASSIGNMENT_RULES,
    KV_STIG_CHECKLISTS,
    KV_STIG_COLLECTION_GRANTS,
    KV_STIG_COLLECTIONS,
    KV_STIG_HOSTS,
    KV_STIG_HOST_BASELINE_ASSIGNMENTS,
    KV_STIG_REVIEWS,
    as_bool,
    dumps_json,
    kv_record,
    new_id,
    now_epoch,
)


class CollectionDeleteBlockedError(ValueError):
    """DELETE rejected because workspace-scoped children still exist."""

    def __init__(self, counts: Dict[str, int]):
        self.counts = dict(counts)
        total = sum(counts.values())
        super().__init__(
            "workspace has dependent data; retry DELETE with cascade=true to remove "
            f"hosts, checklists, reviews, grants, and assignment rows ({total} total)"
        )


def parse_cascade_flag(*values: Any) -> bool:
    for value in values:
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            if value:
                return True
            continue
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
    return False


def collection_child_counts(service, collection_id: str) -> Dict[str, int]:
    """Counts of workspace-scoped KV rows (global baselines are excluded)."""
    counts = {
        "hosts": len(
            kv_client.query_all(
                kv_client.get_collection(service, KV_STIG_HOSTS),
                {"stig_collection_id": collection_id},
            )
        ),
        "checklists": len(
            kv_client.query_all(
                kv_client.get_collection(service, KV_STIG_CHECKLISTS),
                {"stig_collection_id": collection_id},
            )
        ),
        "grants": len(
            kv_client.query_all(
                kv_client.get_collection(service, KV_STIG_COLLECTION_GRANTS),
                {"stig_collection_id": collection_id},
            )
        ),
        "assignment_rules": 0,
        "assignment_overrides": 0,
        "reviews": 0,
    }
    rules_coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    for rec in kv_client.query_all(rules_coll):
        if rec.get("target_stig_collection_id") == collection_id:
            counts["assignment_rules"] += 1
    override_coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    for rec in kv_client.query_all(override_coll):
        if rec.get("target_stig_collection_id") == collection_id:
            counts["assignment_overrides"] += 1
    checklist_ids = {
        rec["_key"]
        for rec in kv_client.query_all(
            kv_client.get_collection(service, KV_STIG_CHECKLISTS),
            {"stig_collection_id": collection_id},
        )
    }
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    for rec in kv_client.query_all(reviews_coll):
        if rec.get("stig_collection_id") == collection_id or rec.get(
            "checklist_id"
        ) in checklist_ids:
            counts["reviews"] += 1
    return counts


def _has_blocking_children(counts: Dict[str, int]) -> bool:
    return any(
        counts.get(key, 0)
        for key in (
            "hosts",
            "checklists",
            "grants",
            "assignment_rules",
            "assignment_overrides",
            "reviews",
        )
    )


def _cascade_delete_workspace_children(
    service, collection_id: str, username: str
) -> Dict[str, int]:
    removed = {
        "hosts": 0,
        "checklists": 0,
        "reviews": 0,
        "grants": 0,
        "assignment_rules": 0,
        "assignment_overrides": 0,
    }
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    cl_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    for checklist in kv_client.query_all(cl_coll, {"stig_collection_id": collection_id}):
        cl_key = checklist["_key"]
        for review in kv_client.query_all(reviews_coll, {"checklist_id": cl_key}):
            kv_client.delete_record(reviews_coll, review["_key"])
            removed["reviews"] += 1
        kv_client.delete_record(cl_coll, cl_key)
        removed["checklists"] += 1

    host_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    for host in kv_client.query_all(host_coll, {"stig_collection_id": collection_id}):
        kv_client.delete_record(host_coll, host["_key"])
        removed["hosts"] += 1

    grants_coll = kv_client.get_collection(service, KV_STIG_COLLECTION_GRANTS)
    for grant in kv_client.query_all(grants_coll, {"stig_collection_id": collection_id}):
        kv_client.delete_record(grants_coll, grant["_key"])
        removed["grants"] += 1

    rules_coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    for rule in kv_client.query_all(rules_coll):
        if rule.get("target_stig_collection_id") != collection_id:
            continue
        kv_client.delete_record(rules_coll, rule["_key"])
        removed["assignment_rules"] += 1

    override_coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    for override in kv_client.query_all(override_coll):
        if override.get("target_stig_collection_id") != collection_id:
            continue
        kv_client.delete_record(override_coll, override["_key"])
        removed["assignment_overrides"] += 1

    for review in kv_client.query_all(reviews_coll, {"stig_collection_id": collection_id}):
        kv_client.delete_record(reviews_coll, review["_key"])
        removed["reviews"] += 1

    return removed


DEFAULT_WORKSPACE_NAME = "Default"
DEFAULT_WORKSPACE_DESCRIPTION = (
    "Holding workspace for checklist imports until they are assigned elsewhere."
)


def _is_default_flag(rec: Optional[Dict[str, Any]]) -> bool:
    return bool(as_bool((rec or {}).get("is_default")))


def list_all_collections(service) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    return kv_client.query_all(coll)


def list_collections(service, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    ensure_default_collection(service, (session or {}).get("user") or "system")
    from services import grants as grants_svc

    grouped = grants_svc.query_all_grants_grouped(service)
    return access.filter_collections_for_user(
        list_all_collections(service), session, grouped
    )


def find_collection_by_name(service, name: str) -> Optional[Dict[str, Any]]:
    want = (name or "").strip().casefold()
    if not want:
        return None
    for rec in list_all_collections(service):
        if (rec.get("name") or "").strip().casefold() == want:
            return rec
    return None


def get_collection(service, key: str) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    return kv_client.get_by_key(coll, key)


def find_default_collection(service) -> Optional[Dict[str, Any]]:
    flagged = [rec for rec in list_all_collections(service) if _is_default_flag(rec)]
    if flagged:
        flagged.sort(key=lambda rec: float(rec.get("updated_at") or 0), reverse=True)
        return flagged[0]
    return find_collection_by_name(service, DEFAULT_WORKSPACE_NAME)


def set_default_collection(service, key: str, username: str) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    chosen = kv_client.get_by_key(coll, key)
    if not chosen:
        raise KeyError(key)
    ts = now_epoch()
    stored = chosen
    for rec in list_all_collections(service):
        want = rec.get("_key") == key
        if _is_default_flag(rec) == want:
            continue
        patch = dict(rec)
        patch["is_default"] = want
        patch["updated_at"] = ts
        patch["updated_by"] = username
        written = kv_client.update_record(coll, rec["_key"], kv_record(patch))
        if want:
            stored = written
    if not _is_default_flag(stored):
        patch = dict(stored)
        patch["is_default"] = True
        patch["updated_at"] = ts
        patch["updated_by"] = username
        stored = kv_client.update_record(coll, key, kv_record(patch))
    return stored


def ensure_default_collection(service, username: str = "system") -> Dict[str, Any]:
    existing = find_default_collection(service)
    if existing:
        if not _is_default_flag(existing):
            return set_default_collection(service, existing["_key"], username)
        return existing
    return create_collection(
        service,
        {
            "name": DEFAULT_WORKSPACE_NAME,
            "description": DEFAULT_WORKSPACE_DESCRIPTION,
            "access_principals": [],
            "is_default": True,
        },
        username,
    )


def create_collection(
    service, body: Dict[str, Any], username: str
) -> Dict[str, Any]:
    name = (body.get("name") or "Untitled").strip() or "Untitled"
    if find_collection_by_name(service, name):
        raise ValueError("workspace name already exists")
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    key = new_id()
    ts = now_epoch()
    if "access_principals" in body:
        principals = body.get("access_principals")
        principals_str = (
            dumps_json(principals) if isinstance(principals, list) else (principals or "[]")
        )
    else:
        principals_str = dumps_json([f"user:{username}"])
    record = kv_record(
        {
            "_key": key,
            "name": name,
            "description": body.get("description") or "",
            "access_principals": principals_str,
            "is_default": bool(as_bool(body.get("is_default"))),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored = kv_client.insert_record(coll, record)
    if _is_default_flag(stored) or not find_default_collection(service):
        stored = set_default_collection(service, stored["_key"], username)
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
        new_name = (body.get("name") or "").strip()
        other = find_collection_by_name(service, new_name)
        if other and other.get("_key") != key:
            raise ValueError("workspace name already exists")
        patch["name"] = new_name or existing.get("name")
    if "description" in body:
        patch["description"] = body["description"]
    if "access_principals" in body:
        val = body["access_principals"]
        patch["access_principals"] = dumps_json(val) if isinstance(val, list) else val
    if "review_accept_principals" in body:
        val = body["review_accept_principals"]
        patch["review_accept_principals"] = (
            dumps_json(val) if isinstance(val, list) else val
        )
    if "is_default" in body:
        patch["is_default"] = bool(as_bool(body.get("is_default")))
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    if _is_default_flag(stored):
        stored = set_default_collection(service, key, username)
    elif not find_default_collection(service):
        stored = set_default_collection(service, key, username)
    audit.log_event("update", "stig_collection", key, username, body)
    return stored


def delete_collection(
    service,
    key: str,
    username: str,
    *,
    cascade: bool = False,
    source: str = "rest",
) -> Dict[str, Any]:
    rec = get_collection(service, key)
    if not rec:
        raise KeyError(key)
    if _is_default_flag(rec):
        raise ValueError(
            "cannot delete the default workspace; mark another workspace as default first"
        )
    counts = collection_child_counts(service, key)
    if _has_blocking_children(counts) and not cascade:
        audit.log_event(
            "delete_blocked",
            "stig_collection",
            key,
            username,
            {"children": counts, "source": source},
        )
        raise CollectionDeleteBlockedError(counts)

    removed: Dict[str, int] = {}
    if cascade and _has_blocking_children(counts):
        removed = _cascade_delete_workspace_children(service, key, username)

    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    kv_client.delete_record(coll, key)
    audit.log_event(
        "delete",
        "stig_collection",
        key,
        username,
        {
            "cascade": bool(cascade and removed),
            "children_before": counts,
            "removed": removed,
            "source": source,
        },
    )
    return {
        "deleted": key,
        "cascade": bool(cascade and removed),
        "removed": removed,
    }
