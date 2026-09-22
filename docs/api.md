# STIG in Splunk — REST API index

Machine-readable contract: **[openapi.yaml](openapi.yaml)** (OpenAPI 3.0.3).

## Base URLs

| Client | URL pattern |
|--------|-------------|
| Management / automation (`curl`, SDK) | `https://<host>:8089/servicesNS/nobody/stigs_in_splunk` |
| Splunk Web (browser, same-origin) | `https://<host>/<locale>/splunkd/__raw/servicesNS/nobody/stigs_in_splunk` |

Paths in the OpenAPI document are relative to that base (e.g. `GET /stig_collections`).

## Authentication

Splunk platform auth only — no app-level OIDC.

- **Management port:** HTTP Basic (`-u user:pass`) or a valid Splunk session token.
- **Splunk Web UI:** session cookie plus `X-Splunk-Form-Key` (CSRF) on `POST`/`PATCH`/`PUT`/`DELETE`, as in `ui/src/api.js`.

Unauthenticated requests receive **401** with `{"error":"authentication required"}`.

## Capabilities

`package/default/restmap.conf` maps Splunk capabilities to HTTP methods:

| Capability | Typical methods |
|------------|-----------------|
| `stig_read` | `GET` |
| `stig_write` | `POST`, `PATCH`, `PUT` |
| `stig_admin` | `DELETE` (and some admin-only writes) |

Grant-based workspace ACLs further restrict which collections, hosts, and reviews a user can see or change.

## Versioning

- **App / contract version** follows `package/app.manifest` → `info.id.version` and `globalConfig.yaml` → `meta.version` (currently **0.1.0**).
- **`docs/openapi.yaml`** is updated in the same PR when persist routes change in `package/bin/stig_rest_handler.py`. There is no separate API version prefix in URLs.
- Breaking REST changes should bump the app minor version and be called out in release notes.

## Resource map (quick)

| Prefix | Purpose |
|--------|---------|
| `/stig_collections` | Workspaces; subpaths for grants, labels, metrics, findings, POA&M, imports, clone, transfer, metadata, … |
| `/stig_hosts` | Assets; `/metadata`, `/checklists`, `/stigs` |
| `/stig_baselines` | STIG library; `/import`, `/jobs`, `/hierarchy`, `/by_stig/{stigId}`, `/rule/{key}`, `/{id}/rules` |
| `/stig_checklists` | Checklists; export, upgrade, validate, `export_bulk` |
| `/stig_reviews` | Reviews; workflow actions; `/batch` |
| `/stig_imports` | File ingest and `/reconcile` |
| `/stig_findings` | Workspace findings (`stig_collection_id` query) |
| `/stig_settings` | Editor / ingest settings (no HEC token in responses) |
| `/stig_assignment_rules`, `/stig_host_baseline_assignments`, `/stig_assignment/preview` | HEC routing |
| `/stigs_in_splunk_baseline` | UCC Configuration table adapter (list/delete baselines) |

Implementation source of truth: `package/bin/stig_rest_handler.py` and `package/default/restmap.conf`.

## Gaps vs STIG Manager OpenAPI

This contract documents **Splunk persist** resources (`stig_*`), not STIG Manager URL literals. User admin, OAuth scopes, async job APIs beyond baseline chunk upload, and SSE live state are out of scope or **n/a** on Splunk — see [FEATURE_PARITY.md](FEATURE_PARITY.md).
