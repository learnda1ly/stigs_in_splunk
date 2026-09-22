import React from "react";
import styled from "styled-components";

export const STATUS_LABELS = {
    not_reviewed: "Not Reviewed",
    open: "Open",
    not_a_finding: "Not a Finding",
    not_applicable: "Not Applicable",
};

export const WORKFLOW_LABELS = {
    draft: "Draft",
    submitted: "Submitted",
    accepted: "Accepted",
    rejected: "Rejected",
};

const PALETTE = {
    not_reviewed: { bg: "#e8eaed", fg: "#3c444d" },
    open: { bg: "#f8d7da", fg: "#721c24" },
    not_a_finding: { bg: "#d4edda", fg: "#155724" },
    not_applicable: { bg: "#cce5ff", fg: "#004085" },
};

const Pill = styled.span`
    display: inline-block;
    max-width: 100%;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    background: ${(p) => p.$bg};
    color: ${(p) => p.$fg};
`;

export function StatusChip({ status }) {
    const key = status || "not_reviewed";
    const pal = PALETTE[key] || PALETTE.not_reviewed;
    return (
        <Pill $bg={pal.bg} $fg={pal.fg}>
            {STATUS_LABELS[key] || key}
        </Pill>
    );
}

export const DEFAULT_REVIEW_REQUIREMENTS = {
    require_finding_details: false,
    require_comments: false,
    min_finding_details_length: 0,
    min_comments_length: 0,
    applies_to_statuses: [],
};

function text(value) {
    return String((value == null ? "" : value) || "").trim();
}

function reviewStatus(rev) {
    return String((rev && rev.status) || "not_reviewed")
        .trim()
        .toLowerCase();
}

export function normalizeReviewRequirements(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const applies = Array.isArray(src.applies_to_statuses)
        ? src.applies_to_statuses
              .map((s) => String(s || "").trim().toLowerCase())
              .filter(Boolean)
        : [];
    return {
        require_finding_details: Boolean(src.require_finding_details),
        require_comments: Boolean(src.require_comments),
        min_finding_details_length: Math.max(
            0,
            parseInt(src.min_finding_details_length, 10) || 0
        ),
        min_comments_length: Math.max(
            0,
            parseInt(src.min_comments_length, 10) || 0
        ),
        applies_to_statuses: applies,
    };
}

export function reviewValidationIssues(rev, policy) {
    const pol = normalizeReviewRequirements(policy || DEFAULT_REVIEW_REQUIREMENTS);
    if (
        pol.applies_to_statuses.length &&
        pol.applies_to_statuses.indexOf(reviewStatus(rev)) < 0
    ) {
        return [];
    }
    const issues = [];
    const details = text(rev && rev.finding_details);
    const comments = text(rev && rev.comments);
    if (
        !pol.require_finding_details &&
        !pol.require_comments &&
        !pol.min_finding_details_length &&
        !pol.min_comments_length
    ) {
        if (!details && !comments) {
            issues.push({
                code: "finding_text_required",
                message:
                    "Finding is not valid when both finding details and comments are empty.",
            });
        }
        return issues;
    }
    if (pol.require_finding_details) {
        const minLen =
            pol.min_finding_details_length > 0
                ? pol.min_finding_details_length
                : 1;
        if (details.length < minLen) {
            issues.push({
                code: details ? "finding_details_too_short" : "finding_details_required",
                message: details
                    ? "Finding details must be at least " + minLen + " characters."
                    : "Finding details are required for this workspace.",
            });
        }
    }
    if (pol.require_comments) {
        const minLen =
            pol.min_comments_length > 0 ? pol.min_comments_length : 1;
        if (comments.length < minLen) {
            issues.push({
                code: comments ? "comments_too_short" : "comments_required",
                message: comments
                    ? "Comments must be at least " + minLen + " characters."
                    : "Comments are required for this workspace.",
            });
        }
    }
    return issues;
}

export function reviewIsValid(rev, policy) {
    if (policy) {
        return reviewValidationIssues(rev, policy).length === 0;
    }
    if (rev && typeof rev.valid === "boolean") {
        return rev.valid;
    }
    return Boolean(
        text(rev && rev.finding_details) || text(rev && rev.comments)
    );
}

export function reviewWorkflowState(rev) {
    const raw = (rev && rev.workflow_state) || "draft";
    return String(raw).toLowerCase();
}

export function reviewIsEditable(rev) {
    if (rev && typeof rev.workflow_editable === "boolean") {
        return rev.workflow_editable;
    }
    return reviewWorkflowState(rev) === "draft";
}

const WF_PALETTE = {
    draft: { bg: "#f0f0f0", fg: "#333" },
    submitted: { bg: "#fff3cd", fg: "#856404" },
    accepted: { bg: "#d4edda", fg: "#155724" },
    rejected: { bg: "#f8d7da", fg: "#721c24" },
};

export function WorkflowChip({ workflowState }) {
    const key = reviewWorkflowState({ workflow_state: workflowState });
    const pal = WF_PALETTE[key] || WF_PALETTE.draft;
    return (
        <Pill $bg={pal.bg} $fg={pal.fg}>
            {WORKFLOW_LABELS[key] || key}
        </Pill>
    );
}
