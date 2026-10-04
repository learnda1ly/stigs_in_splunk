# Feature parity backlog: `stigs_in_splunk` vs STIG Manager

Gap backlog comparing **[STIG Manager](https://github.com/NUWCDIVNPT/stig-manager)** (reference product; read-only) with **`stigs_in_splunk`** (Splunk-native port: KV store, custom persist REST, UCC Configuration, SplunkUI React). One feature PR per row or epic—not an implementation plan for application code in this file.

**Rescored 2026-10-03** (America/Chicago) against:

- STIG Manager docs **latest** (Read the Docs sitemap `lastmod` 2026-09-29): https://stig-manager.readthedocs.io/en/latest/
- App commit [`122f7c49`](https://github.com/learnda1ly/stigs_in_splunk/commit/122f7c49e2ed31606dc5e3a50b9c094a11406540) (`master` at rescore time)

**Repo references:** [spec.md](../spec.md), [docs/openapi.yaml](openapi.yaml), [docs/api.md](api.md), [docs/automation.md](automation.md), [docs/watcher-hec.md](watcher-hec.md).

The prior `docs/FEATURE_PARITY.md` on that commit scored **59 done / 0 partial / 0 missing / 8 n/a** and treated the P0–P1 assessor path as closed. That core path is still in the code (workspaces, grants, editor, collection review, submit/accept/reject, findings, POA&M, CKL/CKLB/XCCDF import and archive export, revision upgrade merge). This rescore does **not** reopen those rows. It downgrades rows whose “done” no longer matches the current user/admin guide, and adds features the old backlog never listed.

**Independence:** `stigs_in_splunk` is not a fork. STIG Manager is a behavioral reference only. Do not copy Node/Express or the GPL-3.0 ExtJS client. See [NOTICE](../NOTICE) and [LICENSE](../LICENSE) (MIT, Stephen Quinlan, 2026).

## How statuses were judged

| Status | Meaning |
|--------|---------|
| **done** | Behavior from the current docs exists in Splunk-shaped REST and/or SplunkUI, verified in this tree |
| **partial** | A path exists; a material behavior from the current docs does not |
| **missing** | No implementation found |
| **n/a** | Splunk platform owns it, or this port **intentionally** decided not to build it (see not-applicable table) |
| **unverified** | Not opened in this pass |

Priorities and sizes match the existing legend: **P0** blocks single-collection assessment, **P1** teams/automation/RMF reporting, **P2** polish and secondary admin. **S** under about a week, **M** several layers, **L** cross-cutting.

## Summary (counts, this pass)

| Status | Count | Notes |
|--------|------:|-------|
| done | 25 | Core assessor/admin path; see “Still done” table |
| partial | 5 | Material doc gaps on existing paths |
| missing | 8 | No implementation found |
| n/a | 8 | Platform-owned or **intentionally out of scope** |
| unverified | 3 | Listed at end of doc |

P0 assessor workflows remain **done** in code; remaining P1/P2 work is guide alignment and hygiene (engineer-day estimates below).

### STE-34 (2026-10-04): unpinned “latest” revision

Unpinned catalog resolution now matches STIG Manager [§2.9.3.2](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html): highest `VxRy` among selectable benchmarks, excluding `draft` / `interim`, with `imported_at` as tie-break only. Workspace `default_baseline_map` pins are unchanged. Code: `find_baseline_by_stig` (`services/baselines.py`), library hierarchy (`services/baseline_library.py`), tests in `tests/test_find_baseline_by_stig.py`.

---

## What changed vs prior `docs/FEATURE_PARITY.md`

| Row | Was | Now | Why |
|-----|-----|-----|-----|
| Default STIG revision per collection | done | **done** | Pin map plus unpinned latest by `VxRy` with draft/interim excluded (STE-34 / `find_baseline_by_stig`). Rescore had flagged `imported_at` ordering; fixed in code. Docs: [§2.9.3.2](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Collection dashboard metrics | done | **done** | `GET /stig_collections/{id}/metrics` includes review ages; `GET .../metrics/export` supports groupings, summary/detail, and result-engine splits (not CORA). Docs: [§2.4.1](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Review aging | done | **partial** | Stale **report** only (`review_aging.py`: threshold + status/severity filters; saved search `stigkvreviewaging`). Docs now specify **action rules** (delete, set Saved/Submitted, set result to Not Checked or Informational), ordinal, enable/disable, and targets (collection, asset, STIG, label). App Manager job **Update Aged Reviews**. Docs: [§2.9.1.7](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html), [admin §2.2.5](https://stig-manager.readthedocs.io/en/latest/admin-guide/admin-guide.html). |
| Result engine (automated / manual / override) | not a row | **done** | `resultEngine` survives ingest via `review_seed_payload` → KV `result_engine` (`collections.conf`, `import_policy.py`). Editor shows manual / automated / override (`ui/src/resultEngine.jsx`, `EditorApp.jsx`). Manual status edits clear engine (`services/reviews.py`). XCCDF archive export emits scanner check + override messages (`exporters/xccdf_results.py`). Docs: [§2.7.1 and §2.7.4.4](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Informational result | folded into status enum | **done** | Fifth assessor status `informational` in `models.py` (`STATUSES`, CKL/CKLB/XCCDF mappings). Import/export, metrics `by_status`, React editor, legacy `stig_editor`, review-aging `set_result_informational`, and import-options unreviewed-with-comment default. |
| Collection import options | not a row | **done** | Per-workspace `import_options` on `stig_collections`; REST `GET/PATCH .../import_options`; applied on file import, batch/zip, HEC apply, and reconcile via `import_policy.py`. Admin UI **Import options**. Docs: [§2.9.1.4.4](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Compare STIG revisions | not a row | **done** | `GET /stig_baselines/compare` + library UI compare panel (`LibraryApp.jsx`). Read-only add/remove/changed report with per-field from/to on changed rules; upgrade merge remains separate. Docs: [§2.3.2.2](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html), [review handling](https://stig-manager.readthedocs.io/en/latest/user-guide/review-handling.html). |
| Review attachments | not a row | **missing** | No review image store. The word “attachment” in the REST handler is not this feature. Docs: [§2.6.5.2 and §2.7.3.2](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Asset CSV import/export | not a row | **done** | `GET/POST /stig_collections/{id}/assets/csv` and SplunkUI **Hosts** import/export (STIG Manager columns). Docs: [§2.9.2.2–2.9.2.3](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Copy results to another collection | not a row | **missing** | `POST .../export-to/{dst}` **moves** hosts (`collection_transfer.py`). It does not copy results onto a same-named asset in the destination (100-asset cap in the docs). Docs: [§2.9.2.5.1](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Multi-STIG `.ckl` in an archive | not a row | **missing** | Export is one checklist file per host+baseline (`exporters/ckl.py`). Docs offer single-STIG vs multi-STIG `.ckl` vs XCCDF. Docs: [§2.9.2.5.2](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Unsubmit | not a row | **missing** | States are `draft` / `submitted` / `accepted` / `rejected` (`review_workflow.py`). Reject returns to draft. There is no unsubmit of a submitted review. Docs: [§2.6.3.1](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Review history retention | done (append + GET) | **partial** | History is append-only. `limit` is a query page size (default 100, max 500), not a per-workspace cap (docs default 15) and history cannot be turned off. Docs: [§2.9.1.4.3](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| `.ckl` web/database asset identity | not a row | **partial** | `WEB_DB_SITE` / `WEB_DB_INSTANCE` are stored. Host match in `apply.py` is hostname only, not host + site + instance when `WEB_OR_DATABASE` is true. Docs: [§2.10](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Effective access preview | not a row | **missing** | Grants and ACL filters exist. No UI/API that expands a grant to every asset×STIG the user can actually touch. `GrantsApp.jsx` has no effective-access view. Docs: [§2.9.1.3](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Delete unmapped reviews | not a row | **missing** | Orphan **baseline rule** GC exists. No job deletes reviews whose rule or STIG assignment is gone. Docs: [admin §2.2.5](https://stig-manager.readthedocs.io/en/latest/admin-guide/admin-guide.html) (Delete Unmapped Reviews / Delete Unmapped Asset Reviews). |
| Replace existing STIG revision on import | not a row | **missing** | Fingerprint dedup keeps the existing revision. No “replace existing revisions” switch. Docs: [admin §2.2.4](https://stig-manager.readthedocs.io/en/latest/admin-guide/admin-guide.html). |
| Clone: pin every STIG + async status | done (sync clone flags) | **partial** | `POST /stig_collections/{id}/clone` copies hosts, checklists, reviews, grants, labels, metadata, baseline defaults, review requirements. It does not offer “pin all STIGs to the source defaults” as its own switch, and it is not a background job with a status bar. Docs: [§2.9.1.1](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |

Rows left **done** were re-checked against code, not just the old table: collections, grants and ACL (host, baseline, label), labels, host transfer, asset CRUD and metadata, assign/remove STIG, checklist import wizard (sync, not SM’s async job), STIG library browse, XCCDF/CKL baseline import, revision **upgrade merge**, rule/CCI/group lookups, asset and collection review workspaces, status workflow submit/accept/reject, review requirements, peer copy, batch review PATCH, ingest lock, CKL/CKLB/XCCDF archive export, Watcher-shaped HEC, baseline chunk jobs and collection archive jobs, findings, aggregate findings, unreviewed reports, POA&M CSV/XLSX, OpenAPI file, settings adapter, cascade delete, orphan rule GC, workspace-scoped baselines, vim editor, `stig:finding` index, reconcile saved search, RMF **package** labels (`services/rmf_packages.py`, commit message “Implement RMF packages”). Those RMF packages are a Splunk ingest-routing feature. They are **not** STIG Manager rule exceptions.

---

## Status table (this pass)

### Still done (evidence, one line)

| Feature | Evidence |
|---------|----------|
| Collections, metadata, cascade delete | `services/collections.py`, UCC workspaces |
| Grants owner/manager/member/restricted + ACL | `services/grants.py`, `ui/src/pages/GrantsApp.jsx` |
| Labels, host transfer | `services/labels.py`, `services/collection_transfer.py` (move, not copy) |
| Asset CRUD, assign/remove STIG | `services/hosts.py`, `POST /stig_hosts/{id}/stigs` |
| STIG library, baseline import, rule/CCI/group GET | `services/baseline_library.py`, `services/baselines.py` |
| Default STIG revision (pin map + unpinned latest) | `services/baseline_defaults.py`, `find_baseline_by_stig` |
| Revision upgrade / hash merge | `services/revision_upgrade.py` |
| Asset review + collection review + batch | `ui/src/pages/EditorApp.jsx`, `CollectionReviewApp.jsx`, `POST /stig_reviews/batch` |
| Submit / accept / reject, requirements, ingest lock | `review_workflow.py`, editor + collection review UI |
| Result engine on reviews (ingest, editor, export) | `importers/ingest.py`, `services/reviews.py`, `exporters/xccdf_results.py`, `ui/src/resultEngine.jsx` |
| Peer copy | `services/review_peers.py` |
| CKL/CKLB/XCCDF results import and archive export | `services/imports.py`, `exporters/ckl.py`, `cklb.py`, `xccdf_results.py` |
| Watcher-shaped HEC | [docs/watcher-hec.md](watcher-hec.md), `importers/events.py` |
| Findings, aggregate, unreviewed, POA&M file | `services/reporting.py`, `exporters/poam.py`, dashboard tabs |
| Metrics counts and export matrix | `aggregate_metrics`, `collection_metrics_export` in `reporting.py` |
| History timeline (not retention policy) | `services/review_history.py`, editor timeline |
| Async baseline upload + collection archive jobs | `services/baseline_jobs.py`, `services/collection_jobs.py` |
| OpenAPI + settings | [docs/openapi.yaml](openapi.yaml), `services/settings.py` |
| Splunk caps, audit index | `access.py`, [docs/audit-index.md](audit-index.md) |
| RMF package labels (Splunk-only) | `services/rmf_packages.py` |

### Partial or missing

| Feature | Status | Evidence |
|---------|--------|----------|
| Dashboard metrics export + ages | done | Grouped export, summary/detail, ages on metrics + export; CORA n/a |
| Review aging actions | partial | Report/config only; no mutating rules |
| Informational result | done | Distinct status; XCCDF `result="informational"` round-trips |
| Import options | done | `services/import_options.py`, `import_policy.py`, ingest in `apply.py` / `checklists.py` |
| Compare revisions | done | Library compare panel + `GET /stig_baselines/compare` |
| Review image attachments | missing | Not in review model |
| Asset CSV | done | `services/asset_csv.py`, `exporters/asset_csv.py`, Hosts UI |
| Copy results across collections | missing | export-to moves the host |
| Multi-STIG CKL | missing | One file per checklist |
| Unsubmit | missing | No transition |
| History retention cap / off switch | partial | Page `limit` only |
| Web/DB asset match | partial | Fields stored; match is hostname |
| Effective access preview | missing | ACL enforced, not explained in UI |
| Delete unmapped reviews | missing | Rule GC ≠ review GC |
| Replace existing benchmark revision | missing | Dedup keeps current |
| Clone pin-all + async | partial | Sync clone with copy flags |

### Not applicable (intentionally out of scope unless product reverses)

| Feature | Why |
|---------|-----|
| OIDC / user directory / user groups / “unavailable” users | Splunk SSO, roles, and accounts. Map grants to Splunk principals. Docs: [authentication](https://stig-manager.readthedocs.io/en/latest/installation-and-setup/authentication.html), [admin users/groups](https://stig-manager.readthedocs.io/en/latest/admin-guide/admin-guide.html). |
| MySQL, stateless API scale-out, `ANALYZE TABLE` | KV store on the search head. |
| Live SSE `/op/state/sse` and experimental log WebSocket | Splunk Web refresh and `splunkd` / `stig_audit`. |
| Experimental full-database JSONL replace (`STIGMAN_EXPERIMENTAL_APPDATA`) | Destructive instance clone. Use Splunk backup. Not an assessor feature. |
| SCAP benchmark maps | Prior decision: Manual STIG + checklist/results, not scanner maps. |
| CORA score | Prior decision in earlier parity docs. Formula is now documented (CAT I/II/III weights 10/4/1; Very High ≥20%, High ≥10%, Low if CAT I = 0 and CAT II/III each &lt;5%). Build only if you explicitly want that rating. [§2.4.1.1](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html). |
| Republished-rule “latest review wins on old revisions” | [Rule exceptions](https://stig-manager.readthedocs.io/en/latest/user-guide/rule-exceptions.html) says STIG Manager is still designing the real approach (0.014% of rules). Do not port the quirk. |
| CIM vulnerability datamodel | Still called Phase 2 in the old backlog. Not required for STIG Manager parity. |

### Unverified this pass

- OpenAPI tag operation counts in the old appendix (external `stig-manager.yaml` not re-counted).
- Whether collection-review column choices persist across sessions (UI code not line-audited for that).
- Full npm transitive license scan (`ui/package-lock.json` not license-audited). No STIG Manager or GPL client tree was found under `package/bin` or `ui/src`.

---

## Remaining work

No new **P0**. Day-to-day assess (open a workspace, assign a STIG, save, submit, accept/reject, export CKL, findings/POA&M) is still implemented.

### Must do before calling the port aligned with the current user guide (P1)

| Item | Size | Engineer-days | Notes |
|------|------|----------------|-------|
| Collection import options, including Watcher/HEC | M | 5–8 | Touches every ingest path — **done** in app |
| Informational as its own status | — | — | **Done** (see status table) |
| Revision compare (rule/field diff) | — | — | **Done** — library compare + `GET /stig_baselines/compare` |
| Review aging **actions** + saved search that mutates | M | 6–10 | Audit every change; do not silent-delete without a dry run |
| Metrics export groupings + review ages (not CORA) | — | — | **Done** in app (CORA remains n/a) |

**P1 total: about 9–15 engineer-days (about 2–3 weeks for one person).**

The wide end is aging actions. That path can corrupt reviews if wrong.

### Nice to have (P2)

| Item | Size | Engineer-days |
|------|------|----------------|
| Review image attachments | M | 4–8 |
| Copy results to another collection (not a move) | M | 4–7 |
| Asset CSV import/export | — | **Done** |
| Multi-STIG CKL in the zip | S | 2–4 |
| Unmapped-review cleanup job | S | 2–4 |
| Web/DB site+instance asset identity | S | 2–3 |
| Effective-access preview | S | 2–3 |
| Clone: pin-all switch + async status | S | 2–4 |
| History cap and disable | S | 1–2 |
| Replace-existing revision on library import | S | 1–2 |
| Unsubmit | S | 1 |

**P2 total: about 24–43 engineer-days.**

Attachments and cross-collection copy dominate that range (KV size, ACL, partial failure).

### Do not schedule

Everything in the n/a table, including CORA, unless you reverse that decision (CORA itself is about 2–4 days on top of the metrics export work).

**All remaining, P1+P2: about 33–58 engineer-days (about 7–12 weeks).** That is the “major work” if the goal is the current user guide plus admin hygiene, not the already-finished P0 path.

---

## License / attribution

| Item | State |
|------|--------|
| App license | MIT, `LICENSE`, copyright 2026 Stephen Quinlan |
| Independence notice | `NOTICE` (not a fork; no GPL client; Watcher is schema-only; no DISA library in-repo) |
| Shipped third-party | `package/LICENSES/MIT License.txt`; Python `lib/*/LICENSE*` for packaging, deprecation, Splunk SDK |
| STIG Manager source in tree | Not found |
| Still open | Transitive npm licenses not re-audited this pass. No other attribution gap found in app source. |

---

## Doc map used

- [Introduction and features](https://stig-manager.readthedocs.io/en/latest/features/index.html)
- [User guide](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html)
- [Grants, roles, ACL](https://stig-manager.readthedocs.io/en/latest/user-guide/roles-and-access.html) (linked from the user-guide TOC; behavior checked via the user-guide grants sections)
- [Review handling](https://stig-manager.readthedocs.io/en/latest/user-guide/review-handling.html)
- [Rule exceptions](https://stig-manager.readthedocs.io/en/latest/user-guide/rule-exceptions.html)
- [Admin guide](https://stig-manager.readthedocs.io/en/latest/admin-guide/admin-guide.html)
- [Home / common tasks](https://stig-manager.readthedocs.io/en/latest/index.html)

---

*STIG Manager is reference only. Update this file when closing gap issues; rescored 2026-10-03 against commit `122f7c49`.*
