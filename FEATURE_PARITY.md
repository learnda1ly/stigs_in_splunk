# FEATURE_PARITY tracker

| # | Area | STIG Manager concept | Status | Notes |
|---|------|----------------------|--------|-------|
| 5 | Save vs submit vs accept/reject | Saved → Submitted → Accepted/Rejected | **done** | `workflow_state` on `stig_reviews`; REST `POST .../submit|accept|reject` and governance batch on `POST .../batch` (field batch unchanged); SplunkUI STIG Editor actions + batch on visible rows; accept via workspace **owner**/**manager** grants, `stig_review_accept`, or `review_accept_principals`. Classic Simple XML editor: **partial**. |

## Workflow state machine

| State | Editable (assessor) | Next actions |
|-------|---------------------|--------------|
| `draft` | Yes (PATCH status, details, comments) | `submit` when valid |
| `submitted` | No | `accept` or `reject` (owner/manager) |
| `accepted` | No (admin bypass) | — |
| `rejected` | N/A (reject sets `draft` + `reject_feedback`) | `submit` again when valid |

Legacy rows without `workflow_state` are treated as `draft`.

## Metrics / search

- **Open findings (governance):** `status=open` and `workflow_state` not `accepted` (see spec §12).
- Checklist `validate` response includes a `workflow` summary block.
