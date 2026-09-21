# FEATURE_PARITY (iteration tracker)

The full STIG Manager gap backlog lives in **[docs/FEATURE_PARITY.md](docs/FEATURE_PARITY.md)**. Update that file when closing parity rows.

## Row #5 — Save vs submit vs accept/reject (**done**)

| State | Editable (REST PATCH / ingest) | Actions |
|-------|-------------------------------|---------|
| `draft` | Yes | `submit` when valid |
| `submitted` | No | `accept` / `reject` (read + owner/manager grant or `review_accept_principals`) |
| `accepted` | No | — |

Reject returns to `draft` and stores optional `reject_feedback`. Legacy rows without `workflow_state` are treated as `draft`.

**Open findings (governance):** `status=open` and `workflow_state` ≠ `accepted` (REST metrics, findings report, spec §12).
