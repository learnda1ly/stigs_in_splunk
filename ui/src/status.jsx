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

export function reviewIsValid(rev) {
    if (rev && typeof rev.valid === "boolean") {
        return rev.valid;
    }
    return Boolean(
        String((rev && rev.finding_details) || "").trim() ||
            String((rev && rev.comments) || "").trim()
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
