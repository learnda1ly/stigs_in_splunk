"""Apply workspace import options to Watcher-shaped findings and review seeds."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import access
import review_workflow
import validation
from importers.ingest import review_seed_payload, status_from_result

COMPLIANCE_RESULTS = frozenset(
    {"pass", "fail", "notapplicable", "fixed", "informational"}
)
UNREVIEWED_RESULTS = frozenset({"notchecked", "notselected", ""})

EMPTY_DETAIL_PLACEHOLDER = "(No finding detail was provided in the imported review.)"
EMPTY_COMMENT_PLACEHOLDER = "(No comment was provided in the imported review.)"


def result_kind(result: Optional[str]) -> str:
    key = str(result or "").strip().lower()
    if key in {"fail", "fixed"}:
        return "fail"
    if key == "pass":
        return "pass"
    if key in {"notapplicable", "not_a_finding"}:
        return "notapplicable"
    return "unreviewed"


def is_unreviewed_result(result: Optional[str]) -> bool:
    return result_kind(result) == "unreviewed"


def should_include_event(event: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    result = event.get("result")
    if not is_unreviewed_result(result):
        return True
    mode = policy.get("include_unreviewed") or "with_comments"
    if mode == "never":
        return False
    if mode == "always":
        return True
    detail = str(event.get("detail") or "").strip()
    comment = str(event.get("comment") or "").strip()
    return bool(detail or comment)


def prepare_event_for_import(event: Dict[str, Any], policy: Dict[str, Any]) -> None:
    """Adjust unreviewed-with-comment result/status before seed extraction."""
    if not is_unreviewed_result(event.get("result")):
        return
    detail = str(event.get("detail") or "").strip()
    comment = str(event.get("comment") or "").strip()
    if not detail and not comment:
        return
    mode = policy.get("unreviewed_with_comment") or "informational"
    if mode == "informational":
        event["result"] = "informational"
        event["_status"] = "informational"
    else:
        event["result"] = "notchecked"
        event["_status"] = "not_reviewed"


def filter_events_for_import(
    events: List[Dict[str, Any]], policy: Dict[str, Any]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for event in events or []:
        if not should_include_event(event, policy):
            continue
        prepare_event_for_import(event, policy)
        out.append(event)
    return out


def _merge_empty_text(
    incoming: str,
    existing: str,
    mode: str,
    placeholder: str,
) -> Tuple[Optional[str], bool]:
    """Return (value, should_patch). None value means leave field unchanged."""
    if str(incoming or "").strip():
        return incoming, True
    mode = mode or "ignored"
    if mode == "ignored":
        return None, False
    if mode == "imported":
        return "", True
    if mode == "replaced":
        return placeholder, True
    return None, False


def resolve_workflow_state(
    *,
    result: Optional[str],
    policy: Dict[str, Any],
    existing: Optional[Dict[str, Any]],
    merged_review: Dict[str, Any],
    collection_rec: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]],
    review_req_policy: Dict[str, Any],
) -> str:
    kind = result_kind(result)
    if kind == "unreviewed":
        return review_workflow.DEFAULT_WORKFLOW_STATE
    setting = (policy.get("status_per_result") or {}).get(kind) or "saved"
    if setting == "keep_existing" and existing and existing.get("_key"):
        return review_workflow.workflow_state(existing)
    if setting == "accepted":
        if access.user_can_accept_reviews(collection_rec, session, grants):
            return "accepted"
        setting = "submitted"
    if setting == "submitted":
        if validation.is_valid(merged_review, review_req_policy):
            return "submitted"
        return review_workflow.DEFAULT_WORKFLOW_STATE
    return review_workflow.DEFAULT_WORKFLOW_STATE


def apply_seed_with_policy(
    *,
    existing: Dict[str, Any],
    seed: Dict[str, Any],
    event: Optional[Dict[str, Any]],
    policy: Dict[str, Any],
    collection_rec: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]],
    review_req_policy: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge incoming seed into a review patch honoring import options."""
    patch = dict(existing)
    result = (event or {}).get("result") if event else None
    if not result and seed.get("status"):
        from models import STATUS_TO_RESULT

        for res, stat in STATUS_TO_RESULT.items():
            if stat == seed.get("status"):
                result = res
                break

    incoming_detail = seed.get("finding_details")
    if incoming_detail is None and "finding_details" in seed:
        incoming_detail = seed.get("finding_details")
    elif incoming_detail is None:
        incoming_detail = (event or {}).get("detail") or ""

    incoming_comment = seed.get("comments")
    if incoming_comment is None and "comments" in seed:
        incoming_comment = seed.get("comments")
    elif incoming_comment is None:
        incoming_comment = (event or {}).get("comment") or ""

    detail_val, patch_detail = _merge_empty_text(
        str(incoming_detail or ""),
        str(existing.get("finding_details") or ""),
        policy.get("empty_detail") or "ignored",
        EMPTY_DETAIL_PLACEHOLDER,
    )
    comment_val, patch_comment = _merge_empty_text(
        str(incoming_comment or ""),
        str(existing.get("comments") or ""),
        policy.get("empty_comment") or "ignored",
        EMPTY_COMMENT_PLACEHOLDER,
    )

    if "status" in seed:
        patch["status"] = seed["status"]
    if patch_detail:
        patch["finding_details"] = detail_val
    if patch_comment:
        patch["comments"] = comment_val
    if "package_id" in seed:
        patch["package_id"] = seed.get("package_id") or ""
    if "result_engine" in seed:
        patch["result_engine"] = seed.get("result_engine") or ""

    merged_for_wf = dict(patch)
    patch["workflow_state"] = resolve_workflow_state(
        result=result,
        policy=policy,
        existing=existing,
        merged_review=merged_for_wf,
        collection_rec=collection_rec,
        session=session,
        grants=grants,
        review_req_policy=review_req_policy,
    )
    return patch


def seed_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    review = {
        "ruleId": event.get("ruleId"),
        "groupId": event.get("groupId"),
        "result": event.get("result"),
        "detail": event.get("detail"),
        "comment": event.get("comment"),
        "_status": event.get("_status") or status_from_result(event.get("result")),
        "package_id": event.get("package_id"),
        "resultEngine": event.get("resultEngine"),
    }
    return review_seed_payload(review)
