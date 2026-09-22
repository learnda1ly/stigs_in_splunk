"""Review submit / accept / reject workflow (STIG Manager–style governance)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import validation

# Splunk-shaped states mapped to STIG Manager concepts:
#   draft     — saved assessor work in progress (SM: saved / not submitted)
#   submitted — awaiting owner acceptance (SM: submitted)
#   accepted  — owner accepted (SM: accepted)
#   rejected  — owner rejected; record returns to draft for editing (SM: rejected)
WORKFLOW_STATES = frozenset({"draft", "submitted", "accepted", "rejected"})

DEFAULT_WORKFLOW_STATE = "draft"

# Allowed transitions: (from_state, action) -> to_state
_TRANSITIONS: Dict[Tuple[str, str], str] = {
    ("draft", "submit"): "submitted",
    ("submitted", "accept"): "accepted",
    ("submitted", "reject"): "draft",
}


def normalize_workflow_state(value: Any) -> str:
    if value is None or value == "":
        return DEFAULT_WORKFLOW_STATE
    key = str(value).strip().lower()
    if key in WORKFLOW_STATES:
        return key
    return DEFAULT_WORKFLOW_STATE


def workflow_state(record: Dict[str, Any]) -> str:
    return normalize_workflow_state(record.get("workflow_state"))


def is_editable(record: Dict[str, Any]) -> bool:
    """Assessor may PATCH finding fields only while draft (including after reject)."""
    return workflow_state(record) == "draft"


def is_ingest_mutable(record: Dict[str, Any]) -> bool:
    """HEC/import/reconcile may change review content only in draft (like REST PATCH)."""
    return is_editable(record)


def is_governance_open_finding(record: Dict[str, Any]) -> bool:
    """Open assessor status that is not owner-accepted (spec §12 reporting)."""
    return record.get("status") == "open" and workflow_state(record) != "accepted"


def transition(
    action: str,
    record: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
) -> str:
    current = workflow_state(record)
    if action == "reject":
        if current != "submitted":
            raise ValueError(
                f"cannot reject review in workflow_state={current}; must be submitted"
            )
        return _TRANSITIONS[("submitted", "reject")]
    key = (current, action)
    if key not in _TRANSITIONS:
        raise ValueError(
            f"cannot {action} review in workflow_state={current}"
        )
    if action == "submit" and not validation.is_valid(record, policy):
        issues = validation.collect_issues(record, policy)
        raise ValueError(
            "cannot submit an incomplete review: "
            + validation.format_issue_messages(issues)
        )
    return _TRANSITIONS[key]


def counts_for_metrics(reviews: list) -> Dict[str, int]:
    """Governance-aware counts for collection progress."""
    out = {
        "draft": 0,
        "submitted": 0,
        "accepted": 0,
        "rejected": 0,
        "open_unaccepted": 0,
    }
    for rec in reviews:
        state = workflow_state(rec)
        out[state] = out.get(state, 0) + 1
        if rec.get("status") == "open" and state != "accepted":
            out["open_unaccepted"] += 1
    return out
