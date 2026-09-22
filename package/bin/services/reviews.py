"""stig_reviews read and update."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import access
import audit
import kv_client
import review_workflow
import validation
from models import KV_STIG_REVIEWS, STATUSES, as_bool, kv_record, now_epoch, normalize_status
from models import KV_STIG_CHECKLISTS, KV_STIG_COLLECTIONS
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import review_requirements as review_requirements_svc

MAX_BATCH_REVIEWS = 500


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


def _policy_for_checklist(
    service, checklist_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    checklist = checklists_svc.get_checklist(service, checklist_id, session)
    if not checklist:
        return review_requirements_svc.default_policy()
    collection_id = checklist.get("stig_collection_id")
    if not collection_id:
        return review_requirements_svc.default_policy()
    try:
        return review_requirements_svc.get_policy(service, collection_id, session)
    except KeyError:
        return review_requirements_svc.default_policy()


def _annotate(
    records: List[Dict[str, Any]],
    policy: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    return [validation.annotate_review(rec, policy) for rec in records]


def _workspace_for_checklist(
    service, checklist_id: str, session: Dict[str, Any], write: bool = False
) -> tuple:
    checklist = checklists_svc.get_checklist(
        service, checklist_id, session, write=write
    )
    if not checklist:
        raise KeyError(checklist_id)
    collection_id = checklist.get("stig_collection_id")
    if not collection_id:
        raise ValueError("checklist missing stig_collection_id")
    rec, _ctx, grants = grants_svc.workspace_context(service, collection_id, session)
    return rec, grants


def _ensure_editable(existing: Dict[str, Any], session: Dict[str, Any]) -> None:
    if review_workflow.is_editable(existing):
        return
    if access.user_has_stig_admin(session):
        return
    state = review_workflow.workflow_state(existing)
    raise PermissionError(
        f"review is not editable in workflow_state={state}; submit or accept/reject via workflow actions"
    )


def _apply_workflow_patch(
    patch: Dict[str, Any],
    action: str,
    username: str,
    reject_feedback: Optional[str] = None,
    policy: Optional[Dict[str, Any]] = None,
) -> None:
    ts = now_epoch()
    next_state = review_workflow.transition(action, patch, policy)
    patch["workflow_state"] = next_state
    if action == "submit":
        patch["submitted_at"] = ts
        patch["submitted_by"] = username
    elif action == "accept":
        patch["accepted_at"] = ts
        patch["accepted_by"] = username
    elif action == "reject":
        patch["rejected_at"] = ts
        patch["rejected_by"] = username
        if reject_feedback is not None:
            patch["reject_feedback"] = str(reject_feedback)
    patch["updated_at"] = ts
    patch["updated_by"] = username


def _workflow_action(
    service,
    key: str,
    action: str,
    username: str,
    session: Dict[str, Any],
    reject_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    checklist_id = existing.get("checklist_id")
    if not checklist_id:
        raise ValueError("review missing checklist_id")
    need_write = action == "submit"
    workspace, grants = _workspace_for_checklist(
        service, checklist_id, session, write=need_write
    )

    if action == "submit":
        if not access.user_can_write_collection(workspace, session, grants):
            raise PermissionError("stig_write required to submit reviews")
    elif action in ("accept", "reject"):
        if not access.user_can_accept_reviews(workspace, session, grants):
            raise PermissionError("stig_review_accept or review owner required")
    else:
        raise ValueError(f"unknown workflow action: {action}")

    policy = review_requirements_svc.get_policy(
        service, workspace["_key"], session
    )
    patch = dict(existing)
    _apply_workflow_patch(
        patch, action, username, reject_feedback=reject_feedback, policy=policy
    )
    patch["valid"] = validation.persistable_valid(patch, policy)
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event(
        action,
        "stig_review",
        key,
        username,
        {"workflow_state": stored.get("workflow_state")},
    )
    return validation.annotate_review(stored, policy)


def submit_review(
    service, key: str, username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    return _workflow_action(service, key, "submit", username, session)


def accept_review(
    service, key: str, username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    return _workflow_action(service, key, "accept", username, session)


def reject_review(
    service,
    key: str,
    username: str,
    session: Dict[str, Any],
    reject_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    return _workflow_action(
        service, key, "reject", username, session, reject_feedback=reject_feedback
    )


def batch_workflow(
    service,
    action: str,
    review_ids: List[str],
    username: str,
    session: Dict[str, Any],
    reject_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    if not review_ids:
        raise ValueError("review_ids must not be empty")
    if len(review_ids) > MAX_BATCH_REVIEWS:
        raise ValueError(f"batch exceeds maximum of {MAX_BATCH_REVIEWS} reviews")

    updated: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for rid in review_ids:
        try:
            if action == "submit":
                updated.append(submit_review(service, rid, username, session))
            elif action == "accept":
                updated.append(accept_review(service, rid, username, session))
            elif action == "reject":
                updated.append(
                    reject_review(
                        service, rid, username, session, reject_feedback=reject_feedback
                    )
                )
            else:
                raise ValueError(f"unknown workflow action: {action}")
        except PermissionError as exc:
            errors.append(
                {"_key": str(rid), "review_id": str(rid), "error": str(exc), "code": "forbidden"}
            )
        except KeyError:
            errors.append(
                {
                    "_key": str(rid),
                    "review_id": str(rid),
                    "error": "not found",
                    "code": "not_found",
                }
            )
        except ValueError as exc:
            errors.append(
                {"_key": str(rid), "review_id": str(rid), "error": str(exc), "code": "invalid"}
            )
    return {
        "action": action,
        "updated": updated,
        "errors": errors,
        "summary": {
            "total": len(review_ids),
            "succeeded": len(updated),
            "failed": len(errors),
        },
    }


def list_reviews(
    service,
    session: Dict[str, Any],
    checklist_id: Optional[str] = None,
    status: Optional[str] = None,
    stig_collection_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    rule_version: Optional[str] = None,
    valid: Optional[Any] = None,
    workflow_state: Optional[str] = None,
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
        policy = review_requirements_svc.get_policy(
            service, rec.get("stig_collection_id"), session
        )
        annotated = _annotate(records, policy)
    else:
        checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
        visible_checklists = {
            c["_key"]
            for c in kv_client.query_all(checklist_coll)
            if c.get("stig_collection_id") in allowed
        }
        records = [r for r in records if r.get("checklist_id") in visible_checklists]
        annotated = _annotate_with_workspace_policies(service, records, session)

    want = _as_bool(valid)
    if want is not None:
        annotated = [r for r in annotated if bool(r.get("valid")) is want]
    if workflow_state:
        want_wf = review_workflow.normalize_workflow_state(workflow_state)
        annotated = [
            r
            for r in annotated
            if review_workflow.workflow_state(r) == want_wf
        ]
    return annotated


def get_review(service, key: str, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    rec = kv_client.get_by_key(coll, key)
    if not rec:
        return None
    checklist_id = rec.get("checklist_id")
    if checklist_id:
        checklists_svc.get_checklist(service, checklist_id, session)
        policy = _policy_for_checklist(service, checklist_id, session)
    else:
        policy = review_requirements_svc.default_policy()
    return validation.annotate_review(rec, policy)


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
    workspace, grants = _workspace_for_checklist(service, checklist_id, session, write=True)
    if not access.user_can_write_collection(workspace, session, grants):
        raise PermissionError("stig_write required")

    content_keys = {"status", "finding_details", "comments", "package_id", "ingest_lock"}
    if any(k in body for k in content_keys):
        _ensure_editable(existing, session)

    patch = dict(existing)
    patch["workflow_state"] = review_workflow.workflow_state(existing)
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
    if "ingest_lock" in body:
        locked = as_bool(body["ingest_lock"])
        if locked is None:
            raise ValueError("ingest_lock must be a boolean")
        patch["ingest_lock"] = bool(locked)
    policy = _policy_for_checklist(service, checklist_id, session)
    issues = validation.collect_issues(patch, policy)
    if any(k in body for k in content_keys) and issues:
        raise ValueError(validation.format_issue_messages(issues))
    patch["valid"] = validation.persistable_valid(patch, policy)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_review", key, username, {"status": stored.get("status")})
    return validation.annotate_review(stored, policy)


def batch_update_reviews(
    service,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """Update many reviews in one request.

    Partial success: each row is applied independently. The response always includes
    ``updated`` and ``errors`` arrays plus a ``summary`` count. HTTP 200 when the
    batch was accepted (even if some rows failed); 400 when the request body is invalid.
    """
    items = body.get("reviews")
    if items is None:
        items = body.get("updates")
    if not isinstance(items, list):
        raise ValueError("reviews must be an array")
    if not items:
        raise ValueError("reviews must not be empty")
    if len(items) > MAX_BATCH_REVIEWS:
        raise ValueError(f"batch exceeds maximum of {MAX_BATCH_REVIEWS} reviews")

    updated: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": index, "error": "each review must be an object"})
            continue
        key = item.get("_key") or item.get("id")
        if not key:
            errors.append({"index": index, "error": "_key is required"})
            continue
        patch = {
            k: v for k, v in item.items() if k not in ("_key", "id")
        }
        if not patch:
            errors.append({"_key": str(key), "error": "no fields to update"})
            continue
        try:
            updated.append(
                update_review(service, str(key), patch, username, session)
            )
        except PermissionError as exc:
            errors.append(
                {"_key": str(key), "error": str(exc), "code": "forbidden"}
            )
        except KeyError:
            errors.append(
                {"_key": str(key), "error": "not found", "code": "not_found"}
            )
        except ValueError as exc:
            errors.append(
                {"_key": str(key), "error": str(exc), "code": "invalid"}
            )

    return {
        "updated": updated,
        "errors": errors,
        "summary": {
            "total": len(items),
            "succeeded": len(updated),
            "failed": len(errors),
        },
    }


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
    policy = review_requirements_svc.get_policy(
        service, checklist.get("stig_collection_id"), session
    )
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    records = kv_client.query_all(coll, {"checklist_id": checklist_id})
    annotated: List[Dict[str, Any]] = []
    valid_count = 0
    for rec in records:
        result = validation.annotate_review(rec, policy)
        if persist and _as_bool(rec.get("valid")) is not result["valid"]:
            patch = dict(rec)
            patch["valid"] = result["valid"]
            stored = kv_client.update_record(coll, rec["_key"], kv_record(patch))
            result = validation.annotate_review(stored, policy)
        if result["valid"]:
            valid_count += 1
        annotated.append(result)
    workflow = review_workflow.counts_for_metrics(annotated)
    return {
        "checklist_id": checklist_id,
        "total": len(annotated),
        "valid": valid_count,
        "invalid": len(annotated) - valid_count,
        "workflow": workflow,
        "reviews": annotated,
    }


def _checklist_collection_map(service) -> Dict[str, str]:
    checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    return {
        c["_key"]: c.get("stig_collection_id") or ""
        for c in kv_client.query_all(checklist_coll)
    }


def _annotate_with_workspace_policies(
    service,
    records: List[Dict[str, Any]],
    session: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not records:
        return []
    checklist_map = _checklist_collection_map(service)
    policy_cache: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []
    for rec in records:
        collection_id = checklist_map.get(rec.get("checklist_id") or "", "")
        if collection_id not in policy_cache:
            try:
                if collection_id:
                    policy_cache[collection_id] = review_requirements_svc.get_policy(
                        service, collection_id, session
                    )
                else:
                    policy_cache[collection_id] = review_requirements_svc.default_policy()
            except KeyError:
                policy_cache[collection_id] = review_requirements_svc.default_policy()
        out.append(
            validation.annotate_review(rec, policy_cache[collection_id])
        )
    return out
