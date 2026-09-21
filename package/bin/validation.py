"""Checklist finding validation.

A review is valid when every rule passes. Add new rules to RULES — do not
hand-edit ``valid`` on records; it is always derived.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

Issue = Tuple[str, str]
RuleFn = Callable[[Dict[str, Any]], Optional[Issue]]


def _text(value: Any) -> str:
    return str(value or "").strip()


def rule_finding_text_required(review: Dict[str, Any]) -> Optional[Issue]:
    """A finding is not valid if both finding details and comments are empty."""
    if _text(review.get("finding_details")) or _text(review.get("comments")):
        return None
    return (
        "finding_text_required",
        "Finding is not valid when both finding details and comments are empty.",
    )


# Later checks append here. Order is display order in validation_errors.
RULES: Tuple[RuleFn, ...] = (rule_finding_text_required,)


def collect_issues(review: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for rule in RULES:
        issue = rule(review)
        if issue:
            issues.append({"code": issue[0], "message": issue[1]})
    return issues


def is_valid(review: Dict[str, Any]) -> bool:
    return not collect_issues(review)


def is_completed(review: Dict[str, Any]) -> bool:
    """Completed findings are those that currently pass validation."""
    return is_valid(review)


def annotate_review(review: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with ``valid`` and ``validation_errors`` (not for KV)."""
    import review_workflow

    out = dict(review)
    out["workflow_state"] = review_workflow.workflow_state(out)
    out["workflow_editable"] = review_workflow.is_editable(out)
    issues = collect_issues(out)
    out["valid"] = not issues
    out["validation_errors"] = issues
    return out


def persistable_valid(review: Dict[str, Any]) -> bool:
    return is_valid(review)
