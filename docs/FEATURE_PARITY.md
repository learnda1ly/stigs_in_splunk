# Feature parity backlog: `stigs_in_splunk` vs STIG Manager

This document compares **[STIG Manager](https://github.com/NUWCDIVNPT/stig-manager)** (reference product; read-only) with **`stigs_in_splunk`** (Splunk-native port: KV store, custom persist REST, UCC Configuration, SplunkUI React). It is a **gap backlog** for iterative parity work—one feature PR per row (or per grouped epic), not an implementation plan for this repo.

**Authoritative references**

| Source | URL |
|--------|-----|
| STIG Manager docs | https://stig-manager.readthedocs.io/en/latest/index.html |
| STIG Manager OpenAPI 3.0 | https://github.com/NUWCDIVNPT/stig-manager/blob/main/api/source/specification/stig-manager.yaml |
| STIG Manager user walkthrough | https://stig-manager.readthedocs.io/en/latest/user-guide/user-quickstart.html |
| `stigs_in_splunk` spec | [spec.md](../spec.md) |
| `stigs_in_splunk` REST | `https://<host>:8089/servicesNS/nobody/stigs_in_splunk` — `stig_collections`, `stig_hosts`, `stig_baselines`, `stig_checklists`, `stig_reviews`, `stig_imports`, `stig_settings` |

**Concept mapping (Splunk-shaped)**

| STIG Manager | `stigs_in_splunk` |
|--------------|-------------------|
| Collection | `stig_collection` (workspace) in KV `stig_collections` |
| Asset | `stig_host` in KV `stig_hosts` |
| STIG on asset / checklist | `stig_checklist` (host + baseline + workspace) |
| Review | `stig_review` (per rule, per checklist) |
| STIG library / benchmark revision | `stig_baseline` + `stig_baseline_rules` (global catalog) |
| Collection grant + ACL | KV `stig_collection_grants` + legacy `access_principals`; Splunk capabilities `stig_read` / `stig_write` / `stig_admin` |
| Watcher / scan ingest | HEC `stig:finding` + `POST /stig_imports` + `stigkvreconcile` saved search |
| Metrics / reports | Intended: Splunk dashboards, `inputlookup`, and (future) REST aggregations |

---

## How to use this backlog

1. Pick a row with **Priority P0 or P1** and **Status** `partial` or `missing`.
2. Open **one GitHub issue** (or epic) per row; link this file and the STIG Manager doc/API pointers in the issue.
3. Implement **one PR** against that issue. Acceptance criteria should come from the **Splunk-shaped “Done when”** column below.
4. After merge, update **Status** and **Gap notes** in this file (follow-up PR).
5. Do not port STIG Manager Node/Express/client code; reimplement behavior against KV + persist REST + Splunk Web.

**Legend — Status**

| Status | Meaning |
|--------|---------|
| **done** | Meets PoC / current spec for this capability |
| **partial** | Core path exists; material UX, API, or policy gaps remain |
| **missing** | Not implemented |
| **n/a** | No sensible Splunk equivalent, or owned by the Splunk platform |

**Legend — Priority**

| Priority | Guidance |
|----------|----------|
| **P0** | Blocks day-to-day assessment workflows comparable to STIG Manager for a single collection |
| **P1** | Important for teams, automation, or RMF-adjacent reporting; can follow P0 |
| **P2** | Polish, admin ergonomics, or parity with secondary STIG Manager features |

**Legend — Size (rough)**

| Size | Guidance |
|------|----------|
| **S** | REST + KV or UI only, &lt; ~1 week human effort |
| **M** | Multiple layers (REST + UI + tests) or non-trivial data model |
| **L** | Cross-cutting (metrics suite, workflow engine, large UI surface) |

---

## Summary (counts)

| Status | Count (approx.) |
|--------|-----------------|
| done | 27 |
| partial | 11 |
| missing | 16 |
| n/a | 8 |

Priorities are suggestions for **this** Splunk port; adjust per your deployment (e.g. heavy automation → bump XCCDF results).

---

## Backlog

### A. Organization & access control

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| Collections (workspaces) | UI: Nav tree, Collection Configuration. API: `GET/POST /collections`, `GET/PATCH/DELETE /collections/{collectionId}` | **done** | Splunk uses `stig_collections`; UCC Workspaces tab + `GET/POST /stig_collections`. Default workspace for imports. | CRUD via REST and Configuration; default workspace enforced; delete rules documented. | P0 | — |
| Collection metadata | API: `/collections/{id}/metadata`, `/metadata/keys/...` | **partial** | `description` on workspace; no arbitrary key/value metadata API. | Optional JSON metadata on `stig_collections`; GET/PATCH documented; searchable via lookup if needed. | P2 | S |
| Collection grants (users & roles) | UI: Grants panel, New Grant. API: `/collections/{id}/grants`, `.../grants/{grantId}` | **done** | KV `stig_collection_grants` with **owner / manager / member / restricted**; REST under `/stig_collections/{id}/grants`; SplunkUI **Workspace grants** page. Legacy `access_principals` still honored (dual-read). | Grant CRUD + role capability matrix documented in spec; tests for roles. | P1 | M |
| Grant ACL (asset/STIG/label scoped) | UI: target icon on grant. API: `PUT .../grants/{grantId}/acl` | **partial** | Host + baseline id filters on restricted grants; enforced on REST list/get/patch and SplunkUI lists. **Labels** not implemented (follow-up). | `PUT/PATCH .../grants/{id}/acl`; restricted users see only allowed hosts/checklists/reviews/metrics. | P1 | L |
| Labels on assets | UI: label assignment, filter. API: `/collections/{id}/labels`, `.../labels/{labelId}/assets` | **missing** | No label entity; host `metadata` JSON only. | KV collection or embedded labels; filter `GET /stig_hosts` and editor by label. | P2 | M |
| Transfer assets between collections | UI: transfer workflow. API: `POST /collections/{id}/export-to/{dstCollectionId}` | **partial** | `PATCH /stig_hosts/{id}` with `stig_collection_id` moves host; checklists follow (spec). No bulk transfer UI. | Bulk move API + UI; audit log per host. | P2 | M |
| Clone collection | API: `POST /collections/{collectionId}/clone` | **missing** | — | Clone workspace with hosts, checklists, reviews (optional flags). | P2 | M |
| Meta-collection dashboard | UI: org-wide metrics. API: `/collections/meta/metrics/...` | **missing** | No cross-workspace UI; SPL can aggregate lookups with care. | Splunk dashboard or `GET` meta-metrics across workspaces user can read. | P2 | L |
| Splunk capabilities / roles | Splunk `authorize.conf` | **done** | `stig_user`, `stig_admin`, caps on REST methods. | Parity doc lists cap matrix; integration test for 403 paths. | P0 | — |
| OIDC / IdP authentication | Keycloak, Okta, etc.; API OAuth scopes `stig-manager:collection:*` | **n/a** | Splunk Web + `requireAuthentication` on REST; use Splunk SSO/SAML. | Document “use Splunk auth”; no parallel IdP in app. | — | — |
| User & user-group admin API | API: `/users`, `/user-groups`, `/user` | **n/a** | Splunk native users/roles. | Map STIG Manager privileges to Splunk roles in admin guide. | — | — |

### B. Assets (hosts) & STIG assignment

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| Asset CRUD | API: `/assets`, `/assets/{assetId}`; bulk `PATCH /assets` delete | **done** | `stig_hosts` CRUD; DELETE needs `stig_admin`. | Documented fields align with CKL target_data. | P0 | — |
| Asset metadata API | API: `/assets/{id}/metadata/...` | **partial** | `metadata` JSON string on host; no key-level REST. | `GET/PATCH` metadata keys or documented JSON patch pattern. | P2 | S |
| Attach STIG to asset (assignment) | UI: Assign STIG on asset. API: `POST /assets/{id}/stigs`, `/collections/{id}/stigs/...` | **done** | **`POST /stig_hosts/{hostId}/stigs`** (idempotent checklist create + review spawn); **`GET .../checklists`**. STIG Editor **Assign STIG** when a host is selected. Duplicate assign returns **200** with `"created": false`. | Explicit “assign baseline to host” UX; idempotent create checklist. | P1 | S |
| Remove STIG from asset | API: `DELETE .../stigs/{benchmarkId}` | **done** | **`DELETE /stig_hosts/{id}/stigs/{baselineIdOrStigId}`** or delete checklist (cascades reviews). | UI/API delete checklist by host+baseline. | P1 | — |
| Bulk asset create / import builder | UI: Import CKL/XCCDF builds collection. API: `POST /collections/{id}/assets` | **partial** | `POST /stig_imports` creates host+baseline+checklist from CKL/CKLB; no collection-level XCCDF **results** archive. | Collection import wizard parity for CKL/CKLB; document gaps for XCCDF results. | P1 | M |
| Asset checklist retrieval | API: `/assets/{id}/checklists`, by STIG | **done** | **`GET /stig_hosts/{id}/checklists`** (ACL-aware). Filter by STIG only via client or `GET /stig_checklists?stig_collection_id=` + baseline metadata. | `GET /stig_hosts/{id}/checklists` or documented query pattern. | P2 | S |

### C. STIG library (baselines / revisions)

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| STIG library browse | UI: STIG Library in nav. API: `/stigs`, `/stigs/{benchmarkId}/revisions/...` | **partial** | `GET /stig_baselines`, `GET /stig_baselines/{id}/rules`; no benchmark-centric hierarchy API. | List baselines with revision metadata; rule detail endpoint stable for UI. | P0 | — |
| Import benchmark content (XCCDF) | API: import flows; DISA Manual XCCDF | **done** | XCCDF parser, dedup via `content_fingerprint`, zip-of-zips via `/stig_baselines/jobs`. | RHEL-scale rule count integration test; dedup 200 response. | P0 | — |
| Import from CKL/CKLB as **baseline** | Supported in SM for content | **done** | `format=ckl|cklb` on baseline import. | Unit tests + Configuration list. | P1 | — |
| Skip SRG/SCAP in library zip | SM library behavior | **done** | Spec: Manual-xccdf only from DISA zips. | Documented in README/spec. | P2 | — |
| Default STIG revision per collection | UI: Collection Settings. User guide: [default revision](https://stig-manager.readthedocs.io/en/latest/index.html) | **done** | `default_baseline_map` on workspace; REST `GET/POST/DELETE .../baseline_defaults`; SplunkUI **Default revisions**; checklist create accepts `stig_id` when default set. Precedence: explicit `baseline_id` &gt; workspace default &gt; catalog match. | Per-workspace default baseline per `stig_id`; new assignments use default. | P1 | M |
| Intelligent revision upgrade / review merge | README feature; API behavior on new revision | **done** | Explicit `POST /stig_checklists/{id}/upgrade` and workspace `POST /stig_collections/{id}/upgrade_checklists` (bulk gated with `require_workspace_write`); composite `(group_id, rule_id)` match; newer `VxRy` required; merges on matching `check_content_hash`; editable drafts with changed hash reset (`finding_details`, `comments`, `reject_feedback` cleared); `ingest_lock` and non-draft `workflow_state` preserved on hash mismatch. Non-atomic KV updates documented. STIG Editor confirm + newer-only picker. | On new baseline revision, merge reviews where hash matches; re-evaluate changed rules only. | P1 | L |
| Delete baseline / revision | API: admin on library | **done** | DELETE baseline + rules; UCC table. | Admin cap; orphan checklist handling documented. | P1 | — |
| CCI / group / rule reference APIs | API: `/stigs/.../rules/{ruleId}`, `/stigs/ccis/{cci}`, groups | **partial** | Rules embedded in baseline import; no top-level `/stigs/rules/{ruleId}` search. | `GET` rule by id across baselines or Splunk lookup export. | P2 | M |
| SCAP benchmark maps | API: `/stigs/scap-maps` | **n/a** | Splunk port targets Manual STIG + checklist workflows; SCAP scanner mapping is optional. | If needed: static map table or n/a documented. | P2 | S |

### D. Reviews & assessment UX

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| Asset review workspace (single STIG) | UI: Evaluation tab. API: `GET/PATCH .../reviews/{assetId}/{ruleId}` | **done** | STIG Editor (React): rule list, status, details, comments, progress. | Status immediate save; details/comments require write; keyboard/vim optional. | P0 | — |
| Collection review workspace (one rule, many assets) | UI: Collection Review. API: batch-oriented review GETs | **done** | SplunkUI **Collection review** view (`stig_collection_review_ui`); batch field PATCH + governance batch (submit/accept/reject on selected or all eligible hosts). | New SplunkUI view: pick baseline+rule, edit rows per host; batch PATCH API. | P0 | L |
| Review status enum | Open / NAF / N/A / Not Reviewed | **done** | Same canonical statuses; CKL/CKLB mapping on export. | Round-trip export tests. | P0 | — |
| Review detail & comments | API: review body fields | **done** | `finding_details`, `comments`; `valid` / `validation_errors` from workspace `review_requirements`. | Required-field policy configurable per workspace (see Collection review requirements). | P0 | — |
| Save vs submit vs accept/reject | UI: Submit, Accept, Reject with feedback | **done** | `workflow_state` on `stig_reviews`; REST submit/accept/reject + governance batch; STIG Editor + Collection review UIs; owner/manager grants + `review_accept_principals`; ingest skips non-draft rows; metrics use governance open findings. | Optional workflow fields on `stig_reviews` + UI actions; owner-only accept/reject. | P1 | L |
| Collection review requirements | UI: Collection Settings `(?)` | **done** | KV `review_requirements` JSON on `stig_collections`; REST `GET/PATCH .../review_requirements`; SplunkUI **Review requirements**; server validation on review PATCH/submit; Editor + Collection review read policy. Default preserves legacy “details or comments” rule. | Workspace settings for required fields, min comment length, etc. | P1 | M |
| Review history | API: `/collections/{id}/review-history`, stats | **missing** | Only `updated_at` / `updated_by` on review. | History collection or indexed audit; UI timeline per rule. | P2 | L |
| Review aging rules | API: `/collections/{id}/tasks/review-aging/config` | **missing** | — | Scheduled search or KV flags for stale reviews; optional notifications. | P2 | M |
| Cross-asset review resources (drag-drop) | UI: Review Resources panel | **missing** | — | Show other hosts’ same rule review in editor sidebar; copy action. | P2 | M |
| Bulk review update | API: `POST .../reviews` batch, `postReviewBatch` | **done** | `POST /stig_reviews/batch` (partial success, max 500 rows). | `POST /stig_reviews/batch` with cap checks. | P1 | M |
| Ingest lock (manual override) | SM: manual authoritative reviews | **done** | `ingest_lock` on review; HEC/reconcile skips. | UI toggle in editor; tests in `test_checklist_ingest`. | P1 | — |

### E. Import / export / automation

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| Import CKL/CKLB checklist | UI: Checklist menu. API: asset/collection import | **done** | `POST /stig_imports`; Import UI; Watcher-shaped events. | HEC + KV apply; workspace default. | P0 | — |
| Import XCCDF **results** (scan) | Multi-source integration in README | **partial** | `POST /stig_imports?format=xccdf-results` parses XCCDF `TestResult` / `rule-result` (OpenSCAP-style); HEC + KV apply. Requires baseline in catalog (or workspace default). No full SCAP data stream bundle ingest. | Map pass/fail to review status; document Evaluate-STIG/SCAP path via HEC or REST. | P1 | L |
| Collection archive export CKL | API: `POST .../archive/ckl` | **partial** | `GET /stig_checklists/{id}/export?format=ckl`; bulk `stig_checklists/export_bulk` zip. | Workspace-scoped bulk export; filename conventions (tests). | P1 | — |
| Collection archive export CKLB | API: `POST .../archive/cklb` | **partial** | Same as CKL for CKLB. | Bulk zip includes all checklists in workspace filter. | P1 | — |
| Collection archive export XCCDF | API: `POST .../archive/xccdf` | **missing** | — | Optional XCCDF results export from KV state. | P2 | L |
| STIGMan Watcher integration | [stigman-watcher](https://github.com/NUWCDIVNPT/stigman-watcher) | **done** | HEC + `events.py` fat events; reconcile every 5m. Event schema and Watcher POST field parity documented in [watcher-hec.md](watcher-hec.md). | Document event schema; parity with Watcher POST fields. | P1 | S |
| Async import/export jobs | API: `/jobs`, `/jobs/{jobId}/runs`, tasks | **partial** | `/stig_baselines/jobs` chunk upload only. | Extend job pattern for large collection import/export if needed. | P2 | M |
| Evaluate-STIG / API automation | OpenAPI entire surface | **partial** | Custom `/stig_*` only; no OpenAPI publish. | Optional `docs/openapi.yaml` for Splunk REST; versioning policy. | P2 | M |

### F. Findings, metrics, POA&M, reporting

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| Collection dashboard metrics | UI: completion, severity, CORA. API: `/collections/{id}/metrics/summary|detail` (+ aggregations) | **done** | SplunkUI **Collection dashboard** + `GET /stig_collections/{id}/metrics`; optional lookup dashboard `stig_collection_metrics_lookup`. No CORA scoring. | SPL dashboard or `GET /stig_collections/{id}/metrics` with counts by status/severity. | P0 | L |
| Findings report (open reviews) | UI: Findings report. API: `GET .../findings` | **done** | SplunkUI findings tab + CSV export; `GET /stig_collections/{id}/findings` and `GET /stig_findings?stig_collection_id=` with pagination. | Dedicated findings endpoint or saved report + CSV export in UI. | P0 | M |
| POA&M spreadsheet generation | UI: Generate POA&M. API: `GET .../poam` | **done** | SplunkUI **POA&M CSV/XLSX** on Collection dashboard; `GET /stig_collections/{id}/poam?format=json\|csv\|xlsx` from governance-open findings; JSON includes SPL `outputcsv` alternative (spec §11.6 / README). eMASS template reference only. | Export CSV/XLSX template from open findings; Splunk `outputcsv` alternative documented. | P1 | M |
| CORA risk scoring | README / dashboard screenshots | **missing** | — | **n/a** unless product requests; else P2 calculator from severity weights in SPL. | P2 | L |
| Aggregated findings by rule/group/CCI | UI: Aggregated Findings panel | **done** | SplunkUI **Aggregated findings** tab; `GET /stig_collections/{id}/findings/aggregate` with `group_by=group_id,rule_id,cci` (governance-open counts; CCI from `stig_baseline_rules`). | `stats` SPL or REST aggregation by `group_id`, `rule_id`, CCI from rules lookup. | P1 | M |
| Unreviewed rules/assets reports | API: `/collections/{id}/unreviewed/rules`, `.../assets` | **done** | SplunkUI **Unreviewed** tab on Collection dashboard; REST `GET /stig_collections/{id}/unreviewed/rules` and `.../assets` with `status=not_reviewed` definition and grant ACL filtering (same as metrics/findings). | REST or saved search returning unreviewed counts per host/baseline. | P1 | M |
| Splunk search / lookups | SM: API-only for reports | **done** | `transforms.conf` + `inputlookup`; spec §12. | Document example SPL in README. | P1 | — |
| CIM / vulnerability datamodel | — | **n/a** | Spec Phase 2. | Optional `stig:finding` CIM mapping. | P2 | M |
| Dedicated audit index / dashboard | SM operational logs | **partial** | `stigs_in_splunk.audit` to splunkd log; no UI. | Index audit events; simple dashboard. | P2 | M |

### G. Platform, operations, API infrastructure

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| OpenAPI 3 contract | `stig-manager.yaml` | **missing** | Undocumented persist REST conventions. | Publish Splunk REST OpenAPI or markdown reference generated from handler. | P2 | M |
| Live state / SSE | API: `/op/state/sse` | **n/a** | Splunk Web polling or custom SSE if needed. | Document refresh strategy in UI. | P2 | S |
| App configuration API | API: `/op/configuration` | **partial** | UCC `stigs_in_splunk_settings.conf`; `GET/POST /stig_settings` (no HEC token). | Settings documented in globalConfig + spec. | P1 | — |
| Horizontal scale / stateless API | Container scale-out | **n/a** | Splunk KV on search head; scale via Splunk architecture. | Deployment guide for SHC/KV. | — | — |
| MySQL persistence | Required | **n/a** | KV store collections. | — | — | — |
| Packaging & install | Docker / binaries | **done** | UCC build, tarball, `link-splunk-app.sh`. | Reproducible CI build artifact. | P0 | — |
| Offline & Splunk integration tests | — | **done** | `tests/test_*.py`, `run_splunk_tests.sh`. | Keep parity-sensitive paths covered when adding features. | P0 | — |

### H. Data lifecycle & admin hygiene

| Feature | STIG Manager (UI + API) | Status | Gap notes | Done when (Splunk-shaped) | Pri | Size |
|---------|-------------------------|--------|-----------|-----------------------------|-----|------|
| Cascade delete collection | SM collection delete semantics | **done** | `DELETE /stig_collections/{id}` blocks with **409** when children exist unless `cascade=true`; removes workspace hosts, checklists, reviews, grants, assignment rules/overrides; global baselines unchanged; UCC blocks non-empty workspace delete (REST cascade). | Defined cascade or block delete with children. | P1 | M |
| Orphan baseline rule GC | — | **missing** | Known PoC limitation (spec §17). | Admin REST job to clean orphans. | P2 | S |
| Workspace-scoped baseline catalog | — | **missing** | Baselines global (spec Phase 2). | Optional `stig_collection_id` on baselines or sharing ACL. | P2 | L |

### I. Splunk-specific enhancements (not in STIG Manager)

| Feature | STIG Manager | Status | Notes |
|---------|--------------|--------|-------|
| Vim-style editor shortcuts | — | **done** | Extra UX in React editor; optional. |
| Indexed `stig:finding` events for replay | — | **done** | Enables reconstructing checklists from index + KV. |
| Scheduled KV reconcile | — | **done** | `savedsearches.conf` + `\| stigkvreconcile`. |

---

## Suggested iteration order (P0 first)

1. **Collection review workspace** + batch review API (unblocks multi-asset assessors).
2. **Collection metrics** + **findings report** (dashboard or REST + CSV).
3. **Default baseline per workspace** + **XCCDF results import** (automation-heavy sites).
4. **Grants / ACL refinement** (restricted users with asset filters).
5. **Submit / accept / reject** workflow (governance-heavy sites).
6. **POA&M export** and **aggregated findings** (RMF reporting).
7. **Cross-revision review merge** (operational cost when DISA publishes updates).

---

## Appendix: STIG Manager API tag coverage

OpenAPI **tags** (approximate operation counts from `stig-manager.yaml`): Collection (49), Asset (23), Metrics (16), STIG (15), Review (15), User (13), Job (11), Operation (9).

**Splunk persist resources implemented today** (see `package/bin/stig_rest_handler.py`, `spec.md` §11):

| Resource | Notes |
|----------|--------|
| `stig_collections` | Workspace CRUD |
| `stig_hosts` | Asset CRUD, move workspace, **assign STIG** (`POST .../stigs`), list host checklists |
| `stig_baselines` | List, import, rules, delete, `jobs` chunk import |
| `stig_checklists` | CRUD, export, `export_bulk` |
| `stig_reviews` | List, get, patch (`ingest_lock`), batch (`/batch`) |
| `stig_imports` | CKL/CKLB ingest, reconcile |
| `stig_settings` | Editor settings adapter |
| `stig_findings` | Paginated workspace findings report (`stig_collection_id` query param) |
| `stig_collections/{id}/metrics` | Workspace metrics subpath on collections handler |
| `stig_collections/{id}/findings` | Workspace findings subpath on collections handler |
| `stig_collections/{id}/findings/aggregate` | Governance-open findings counts by group, rule, CCI |
| `stig_collections/{id}/baseline_defaults` | Workspace default baseline per STIG id |
| `stig_collections/{id}/review_requirements` | Workspace review validation policy (GET/PATCH) |
| `stig_collections/{id}/poam` | POA&M-style CSV/XLSX/JSON export |
| `stig_collections/{id}/unreviewed/rules` | Unreviewed rule counts with host coverage |
| `stig_collections/{id}/unreviewed/assets` | Unreviewed counts per host with per-baseline breakdown |
| UCC `stigs_in_splunk_baseline` | Configuration table adapter |

For any new capability, prefer **adding Splunk-shaped endpoints** under these resources (or `stig_collections/{id}/...` subpaths implemented in the persist handler) rather than mirroring STIG Manager URL literals, while keeping response shapes familiar to API migrators.

---

*Generated for parity planning; STIG Manager is reference only. Update this file when closing gap issues.*
