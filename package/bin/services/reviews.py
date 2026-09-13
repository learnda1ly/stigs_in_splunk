"""stig_reviews read and update."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import audit
import kv_client
import validation
from models import KV_STIG_REVIEWS, STATUSES, kv_record, now_epoch, normalize_status
from models import KV_STIG_CHECKLISTS
from services import checklists as checklists_svc
from services import collections as collections_svc


def _as_bool(value) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None


def _annotate(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [validation.annotate_review(rec) for rec in records]


def list_reviews(
    service,
    session: Dict[str, Any],
    checklist_id: Optional[str] = None,
    status: Optional[str] = None,
    stig_collection_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    rule_version: Optional[str] = None,
    valid: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    query: Dict[str, Any] = {}
    if checklist_id:
        query["checklist_id"] = checklist_id
    if status:
        query["status"] = status
    if rule_id:
        query["rule_id"] = rule_id
    if rule_version:
        query["rule_version"] = rule_version
    records = kv_client.query_all(coll, query if query else None)

    allowed = {r["_key"] for r in collections_svc.list_collections(service, session)}
    if stig_collection_id:
        if stig_collection_id not in allowed:
            return []
        allowed = {stig_collection_id}

    if checklist_id:
        rec = checklists_svc.get_checklist(service, checklist_id, session)
        if not rec:
            return []
        if rec.get("stig_collection_id") not in allowed:
            return []
    else:
        checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
        visible_checklists = {
            c["_key"]
            for c in kv_client.query_all(checklist_coll)
            if c.get("stig_collection_id") in allowed
        }
        records = [r for r in records if r.get("checklist_id") in visible_checklists]

    annotated = _annotate(records)
    want = _as_bool(valid)
    if want is not None:
        annotated = [r for r in annotated if bool(r.get("valid")) is want]
    return annotated


def get_review(service, key: str, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    rec = kv_client.get_by_key(coll, key)
    if not rec:
        return None
    checklist_id = rec.get("checklist_id")
    if checklist_id:
        checklists_svc.get_checklist(service, checklist_id, session)
    return validation.annotate_review(rec)


def update_review(
    service, key: str, body: Dict[str, Any], username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    checklist_id = existing.get("checklist_id")
    if not checklist_id:
        raise ValueError("review missing checklist_id")
    checklists_svc.get_checklist(service, checklist_id, session, write=True)

    patch = dict(existing)
    if "status" in body:
        status = normalize_status(body["status"], source="internal") or normalize_status(
            body["status"], source="cklb"
        )
        if status not in STATUSES:
            raise ValueError(f"invalid status: {body['status']}")
        patch["status"] = status
    if "finding_details" in body:
        patch["finding_details"] = body["finding_details"]
    if "comments" in body:
        patch["comments"] = body["comments"]
    if "package_id" in body:
        patch["package_id"] = "" if body["package_id"] is None else str(body["package_id"])
    patch["valid"] = validation.persistable_valid(patch)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_review", key, username, {"status": stored.get("status")})
    return validation.annotate_review(stored)


def validate_checklist(
    service,
    checklist_id: str,
    session: Dict[str, Any],
    persist: bool = False,
) -> Dict[str, Any]:
    checklist = checklists_svc.get_checklist(
        service, checklist_id, session, write=persist
    )
    if not checklist:
        raise KeyError(checklist_id)
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    records = kv_client.query_all(coll, {"checklist_id": checklist_id})
    annotated: List[Dict[str, Any]] = []
    valid_count = 0
    for rec in records:
        result = validation.annotate_review(rec)
        if persist and _as_bool(rec.get("valid")) is not result["valid"]:
            patch = dict(rec)
            patch["valid"] = result["valid"]
            stored = kv_client.update_record(coll, rec["_key"], kv_record(patch))
            result = validation.annotate_review(stored)
        if result["valid"]:
            valid_count += 1
        annotated.append(result)
    return {
        "checklist_id": checklist_id,
        "total": len(annotated),
        "valid": valid_count,
        "invalid": len(annotated) - valid_count,
        "reviews": annotated,
    }
