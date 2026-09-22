"""Checklist finding validation.

A review is valid when every rule passes for the workspace policy. Add new
rules to ``build_rules`` — do not hand-edit ``valid`` on records; it is always
derived.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

Issue = Tuple[str, str]
RuleFn = Callable[[Dict[str, Any], Dict[str, Any]], Optional[Issue]]

DEFAULT_POLICY: Dict[str, Any] = {
    "require_finding_details": False,
    "require_comments": False,
    "min_finding_details_length": 0,
    "min_comments_length": 0,
    "applies_to_statuses": [],
}


def default_policy() -> Dict[str, Any]:
    return dict(DEFAULT_POLICY)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _review_status(review: Dict[str, Any]) -> str:
    return str(review.get("status") or "not_reviewed").strip().lower()


def _policy_applies(review: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    scopes = policy.get("applies_to_statuses") or []
    if not scopes:
        return True
    return _review_status(review) in scopes


def rule_finding_text_required(
    review: Dict[str, Any], policy: Dict[str, Any]
) -> Optional[Issue]:
    """Legacy default: at least one of finding details or comments is non-empty."""
    if policy.get("require_finding_details") or policy.get("require_comments"):
        return None
    if policy.get("min_finding_details_length") or policy.get("min_comments_length"):
        return None
    if _text(review.get("finding_details")) or _text(review.get("comments")):
        return None
    return (
        "finding_text_required",
        "Finding is not valid when both finding details and comments are empty.",
    )


def rule_finding_details_required(
    review: Dict[str, Any], policy: Dict[str, Any]
) -> Optional[Issue]:
    if not policy.get("require_finding_details"):
        return None
    min_len = int(policy.get("min_finding_details_length") or 0)
    if min_len < 1:
        min_len = 1
    details = _text(review.get("finding_details"))
    if len(details) < min_len:
        if not details:
            return (
                "finding_details_required",
                "Finding details are required for this workspace.",
            )
        return (
            "finding_details_too_short",
            f"Finding details must be at least {min_len} characters.",
        )
    return None


def rule_comments_required(
    review: Dict[str, Any], policy: Dict[str, Any]
) -> Optional[Issue]:
    if not policy.get("require_comments"):
        return None
    min_len = int(policy.get("min_comments_length") or 0)
    if min_len < 1:
        min_len = 1
    comments = _text(review.get("comments"))
    if len(comments) < min_len:
        if not comments:
            return (
                "comments_required",
                "Comments are required for this workspace.",
            )
        return (
            "comments_too_short",
            f"Comments must be at least {min_len} characters.",
        )
    return None


def build_rules(policy: Optional[Dict[str, Any]] = None) -> Tuple[RuleFn, ...]:
    _ = policy  # reserved for future policy-specific rule sets
    return (
        rule_finding_text_required,
        rule_finding_details_required,
        rule_comments_required,
    )


def collect_issues(
    review: Dict[str, Any], policy: Optional[Dict[str, Any]] = None
) -> List[Dict[str, str]]:
    pol = policy if policy is not None else default_policy()
    if not _policy_applies(review, pol):
        return []
    issues: List[Dict[str, str]] = []
    for rule in build_rules(pol):
        issue = rule(review, pol)
        if issue:
            issues.append({"code": issue[0], "message": issue[1]})
    return issues


def is_valid(review: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> bool:
    return not collect_issues(review, policy)


def is_completed(review: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> bool:
    """Completed findings are those that currently pass validation."""
    return is_valid(review, policy)


def annotate_review(
    review: Dict[str, Any], policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Return a copy with ``valid`` and ``validation_errors`` (not for KV)."""
    import review_workflow

    out = dict(review)
    out["workflow_state"] = review_workflow.workflow_state(out)
    out["workflow_editable"] = review_workflow.is_editable(out)
    issues = collect_issues(out, policy)
    out["valid"] = not issues
    out["validation_errors"] = issues
    return out


def persistable_valid(
    review: Dict[str, Any], policy: Optional[Dict[str, Any]] = None
) -> bool:
    return is_valid(review, policy)


def format_issue_messages(issues: List[Dict[str, str]]) -> str:
    if not issues:
        return "review validation failed"
    return "; ".join(item.get("message") or item.get("code") or "invalid" for item in issues)
