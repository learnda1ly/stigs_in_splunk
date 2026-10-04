"""Admin GC for reviews that no longer map to a checklist (STIG assignment) or baseline rule."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import audit
import kv_client
from models import KV_STIG_BASELINE_RULES, KV_STIG_CHECKLISTS, KV_STIG_REVIEWS
from models import KV_STIG_REVIEW_HISTORY
from services import baselines as baselines_svc

REASON_MISSING_CHECKLIST = "missing_checklist"
REASON_MISSING_BASELINE = "missing_baseline"
REASON_MISSING_RULE = "missing_rule"


def _rule_identity(rule: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(rule.get("group_id") or ""),
        str(rule.get("rule_id") or ""),
    )


def _baseline_rule_index(service) -> Dict[str, Set[Tuple[str, str]]]:
    """Map baseline_id -> set of (group_id, rule_id) from stig_baseline_rules."""
    rules_coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)
    index: Dict[str, Set[Tuple[str, str]]] = {}
    for rule in kv_client.query_all(rules_coll):
        bid = (rule.get("baseline_id") or "").strip()
        if not bid:
            continue
        gid, rid = _rule_identity(rule)
        if not (gid and rid):
            continue
        index.setdefault(bid, set()).add((gid, rid))
    return index


def _checklist_index(service) -> Dict[str, Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    return {
        str(rec["_key"]): rec
        for rec in kv_client.query_all(coll)
        if rec.get("_key")
    }


def _unmapped_reason(
    review: Dict[str, Any],
    checklists: Dict[str, Dict[str, Any]],
    rule_index: Dict[str, Set[Tuple[str, str]]],
    baseline_ids: Set[str],
) -> Optional[str]:
    checklist_id = (review.get("checklist_id") or "").strip()
    if not checklist_id or checklist_id not in checklists:
        return REASON_MISSING_CHECKLIST

    checklist = checklists[checklist_id]
    baseline_id = (checklist.get("baseline_id") or review.get("baseline_id") or "").strip()
    if not baseline_id or baseline_id not in baseline_ids:
        return REASON_MISSING_BASELINE

    rules = rule_index.get(baseline_id, set())
    gid, rid = _rule_identity(review)
    if not (gid and rid):
        return REASON_MISSING_RULE
    if (gid, rid) in rules:
        return None
    return REASON_MISSING_RULE


def _review_summary(review: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "_key": review.get("_key"),
        "checklist_id": review.get("checklist_id"),
        "baseline_id": review.get("baseline_id"),
        "rule_id": review.get("rule_id"),
        "group_id": review.get("group_id"),
        "reason": reason,
    }


def find_unmapped_reviews(
    service,
    *,
    stig_collection_id: str = "",
) -> List[Dict[str, Any]]:
    """Reviews whose checklist is gone or whose rule is absent from the checklist baseline."""
    scope = (stig_collection_id or "").strip()
    checklists = _checklist_index(service)
    baseline_ids = {
        rec.get("_key")
        for rec in baselines_svc.list_baselines(service)
        if rec.get("_key")
    }
    rule_index = _baseline_rule_index(service)

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    unmapped: List[Dict[str, Any]] = []
    for review in kv_client.query_all(reviews_coll):
        if scope:
            checklist_id = (review.get("checklist_id") or "").strip()
            checklist = checklists.get(checklist_id)
            if not checklist or (checklist.get("stig_collection_id") or "") != scope:
                continue
        reason = _unmapped_reason(review, checklists, rule_index, baseline_ids)
        if reason:
            unmapped.append(review)
    return unmapped


def _delete_review_and_history(
    service, review: Dict[str, Any], username: str
) -> int:
    key = (review.get("_key") or "").strip()
    if not key:
        return 0
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    history_coll = kv_client.get_collection(service, KV_STIG_REVIEW_HISTORY)
    existing = kv_client.get_by_key(reviews_coll, key)
    if not existing:
        return 0
    removed_history = 0
    for row in kv_client.query_all(history_coll, {"review_id": key}):
        hist_key = row.get("_key")
        if hist_key:
            kv_client.delete_record(history_coll, hist_key)
            removed_history += 1
    kv_client.delete_record(reviews_coll, key)
    return removed_history


def gc_unmapped_reviews(
    service,
    username: str,
    *,
    execute: bool = False,
    stig_collection_id: str = "",
) -> Dict[str, Any]:
    """Report or delete unmapped reviews (dry-run unless ``execute`` is True)."""
    unmapped = find_unmapped_reviews(
        service, stig_collection_id=stig_collection_id
    )
    skipped_no_key = sum(1 for r in unmapped if not (r.get("_key") or "").strip())
    summaries: List[Dict[str, Any]] = []
    checklists = _checklist_index(service)
    baseline_ids = {
        rec.get("_key")
        for rec in baselines_svc.list_baselines(service)
        if rec.get("_key")
    }
    rule_index = _baseline_rule_index(service)
    for review in unmapped:
        reason = _unmapped_reason(review, checklists, rule_index, baseline_ids) or ""
        summaries.append(_review_summary(review, reason))

    result: Dict[str, Any] = {
        "dry_run": not execute,
        "unmapped_count": len(unmapped),
        "unmapped": summaries,
        "deleted_count": 0,
        "skipped_no_key_count": skipped_no_key,
        "history_rows_removed": 0,
    }
    if stig_collection_id:
        result["stig_collection_id"] = stig_collection_id.strip()

    if not execute:
        return result

    deleted = 0
    history_removed = 0
    for review in unmapped:
        key = (review.get("_key") or "").strip()
        if not key:
            continue
        history_removed += _delete_review_and_history(service, review, username)
        deleted += 1

    result["dry_run"] = False
    result["deleted_count"] = deleted
    result["history_rows_removed"] = history_removed
    if deleted > 0:
        audit.log_event(
            "gc_unmapped_reviews",
            "stig_reviews",
            None,
            username,
            {
                "deleted_count": deleted,
                "unmapped_count": len(unmapped),
                "skipped_no_key_count": skipped_no_key,
                "history_rows_removed": history_removed,
                "stig_collection_id": (stig_collection_id or "").strip() or None,
            },
        )
    return result
