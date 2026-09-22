# STIG in Splunk (PoC)

Minimal Splunk app that stores DISA STIG baseline and checklist **review** state in the KV store and exposes a custom REST API.

See [spec.md](spec.md) for the full build specification.

For a gap backlog vs [STIG Manager](https://github.com/NUWCDIVNPT/stig-manager) (reference only), see [docs/FEATURE_PARITY.md](docs/FEATURE_PARITY.md).

Watcher / HEC **`stig:finding`** event schema (STIGMan Watcher parity): [docs/watcher-hec.md](docs/watcher-hec.md).

## Build with Splunk UCC

This app is packaged with the [Splunk UCC framework](https://splunk.github.io/addonfactory-ucc-generator/) (`ucc-gen`). Source lives under `package/`; the installable app is produced under `output/stigs_in_splunk`.

### One-time setup

```bash
python3 -m venv .venv-ucc
.venv-ucc/bin/pip install -r requirements-ucc.txt
```

Install from PyPI, not GitHub. The git checkout does not ship `entry_page.js`, so the Configuration page is a blank white screen.

Optional (integration tests / scripts only — not shipped in the built app):

```bash
./scripts/vendor_splunk_sdk.sh   # vendored splunklib into repo lib/
```

### Build and package

```bash
./scripts/build_ucc.sh              # -> output/stigs_in_splunk/
./scripts/package_ucc.sh            # -> output/stigs_in_splunk-0.1.0.tar.gz
```

Install on Splunk: extract the tarball into `$SPLUNK_HOME/etc/apps/` or use Splunk Web → Manage Apps → Install app from file.

### Local dev mount

After a build, bind-mount the **built** app (not the repo root):

```bash
./scripts/link-splunk-app.sh
sudo systemctl restart Splunkd
```

`STIG_APP_SOURCE` defaults to `output/stigs_in_splunk`. After `./scripts/build_ucc.sh`, remount if that directory is bind-mounted (`./scripts/link-splunk-app.sh umount && ./scripts/link-splunk-app.sh`) so Splunk is not left on a deleted folder. Then restart Splunk. Edit Python under `package/bin/` and re-run `./scripts/build_ucc.sh` before restarting Splunk.

### UCC layout

| Path | Role |
|------|------|
| `globalConfig.yaml` | UCC meta plus Configuration tabs (workspaces, editor/ingest) |
| `package/` | App source copied into the build (`bin/`, `default/*.conf`, `metadata/`, `app.manifest`) |
| `package/lib/requirements.txt` | `splunktaucclib` for UCC Configuration REST (pip-installed into `output/.../lib`) |
| `additional_packaging.py` | Post-build: KV reload trigger, keep UCC Configuration view, restore custom nav |
| `output/stigs_in_splunk/` | Generated `app.conf`, Configuration REST handlers, built artifact |

Custom REST uses a **persist** handler (`package/bin/stig_rest_handler.py`) and hand-written `restmap.conf` / `web.conf` (UCC does not generate these for conf-only apps).

### STIG Editor (Splunk Web UI)

Default views are **SplunkUI** (React / `@splunk/react-ui`) pages:

- **STIG Editor** — workspace + host filters, finding list, status, details, comments
- **Collection review** — one baseline rule across all hosts in a workspace (batch save)
- **Import** — checklists (`.ckl` / `.cklb` / `.zip` archive → HEC and KV; multi-file queue in UI) and STIG baselines (single XCCDF, CKL/CKLB, or a DISA product/quarterly zip via chunked persist REST `/stig_baselines/jobs`) on one page with **Checklists** and **Baselines** sections
- **Export** — CKL / CKLB download; bulk zip by selection or workspace archive (`POST /stig_collections/{id}/archive/ckl|cklb`)
- **Configuration** — UCC-generated page for workspaces and editor/HEC settings. A **Default** workspace is created automatically; checklist imports with no workspace go there until you move the host. The HEC token stays on the Splunk `stig_findings` input and is never returned to the browser.

Classic Simple XML + jQuery views remain under the **Classic** nav menu.

Rebuild UI bundles after changing `ui/src`:

```bash
./scripts/build_ui.sh
```

`./scripts/build_ucc.sh` runs that step unless `SKIP_UI_BUILD=1`.

After install, open the app → **STIG Editor**. Use **Collection review** to work one rule across all hosts in a workspace (batch save). Manage workspaces under **Configuration**; import baselines and checklists under **Import**. Imports without a workspace go to **Default**. Choose a workspace, then edit reviews in a split pane. Status saves immediately; finding details and comments require **Write**. **Submit** sends a completed finding for owner **Accept** / **Reject** (workspace **owner** / **manager** grants or `review_accept_principals`; `stig_review_accept` alone does not accept on every readable workspace). See [docs/FEATURE_PARITY.md](docs/FEATURE_PARITY.md) and [FEATURE_PARITY.md](FEATURE_PARITY.md).

Batch review field updates: `POST .../stig_reviews/batch` with `{ "reviews": [{ "_key": "...", "status": "open", ... }] }`. Batch governance: same path with `{ "action": "submit|accept|reject", "review_ids": ["..."] }`. Partial success is supported (per-row errors in the response).

## Splunk roles

Assign `stig_user` or `stig_admin`, or grant capabilities `stig_read`, `stig_write`, `stig_review_accept`, `stig_admin` (see `package/default/authorize.conf`; `role_stig_admin` / `role_admin` include accept/reject for PoC).

## REST base URL

```text
https://<host>:8089/servicesNS/nobody/stigs_in_splunk
```

Resources: `stig_collections` (including `/{id}/grants`, `/{id}/baseline_defaults`, `/{id}/review_requirements`, `/{id}/metrics`, `/{id}/findings`), `stig_hosts`, `stig_baselines`, `stig_checklists`, `stig_reviews`, `stig_imports`, `stig_assignment_rules`.

**Delete workspace:** `DELETE /stig_collections/{id}` requires **stig_admin**. If the workspace still has hosts, checklists, grants, or assignment rows, the API returns **409** unless you pass `?cascade=true` (or JSON `{"cascade": true}`), which removes those workspace-scoped rows and leaves **global baselines** unchanged. The UCC **Workspaces** tab only deletes empty workspaces (Splunk’s table delete confirm); use REST for cascade.

## Example flow (curl)

Quick baseline import (single XCCDF). Large DISA library zips must use chunked `/stig_baselines/jobs`, not one POST:

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_baselines/import?format=xccdf&source_uri=minimal_benchmark.xml" \
  --data-binary @tests/fixtures/minimal_benchmark.xml

# Library zip (~360MB): chunked persist jobs, never UCC/EAI
# 1) POST /stig_baselines/jobs  {"filename":"U_SRG-STIG_Library.zip","size":377487360}
# 2) POST /stig_baselines/jobs/<id>  {"action":"chunk","offset":0,"data":"<base64>"}  (4MB each)
# 3) POST /stig_baselines/jobs/<id>  {"action":"finalize"}
# 4) POST /stig_baselines/jobs/<id>  {"action":"import","path":"...Manual-xccdf.xml"}
```

Checklist file ingest (indexes `stig:finding` via HEC, then updates KV). Omit `stig_collection_id` to use the Default workspace. Re-importing the same host + STIG updates reviews in place (**200**) unless a finding is `ingest_lock`ed.

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=cklb&stig_collection_id=COLLECTION_ID&source_uri=host.cklb" \
  --data-binary @path/to/host.cklb
```

Collection import builder (automation): batch CKL/CKLB into one workspace — per-file success/errors. HTTP status matches single-file import: **201** when any row created a new host/checklist, **200** when all rows succeeded as updates or when any row failed (partial batch).

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_collections/COLLECTION_ID/imports" \
  -H "Content-Type: application/json" \
  -d '{"files":[{"source_uri":"web-01.ckl","format":"ckl","content":"..."}]}'
```

Zip archive of checklists and/or XCCDF scan results (nested zips supported):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=zip&stig_collection_id=COLLECTION_ID&source_uri=hosts.zip" \
  --data-binary @hosts.zip
```

XCCDF-only results archive (skips `.ckl`/`.cklb` members):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=xccdf-results-zip&stig_collection_id=COLLECTION_ID&source_uri=scan-results.zip" \
  --data-binary @scan-results.zip
```

Supported archive shape: one XML file per host scan with an XCCDF 1.2 `TestResult` root (or embedded `TestResult`) and `rule-result` children — typical OpenSCAP `*-results.xml` or Evaluate-STIG output. **Not supported:** ingesting full SCAP source data stream bundles as a single parsed artifact (import Manual STIG baselines separately).

Single-file XCCDF scan results. Import the matching Manual STIG baseline first (or set a workspace default revision):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=xccdf-results&stig_collection_id=COLLECTION_ID&source_uri=host-results.xml" \
  --data-binary @tests/fixtures/minimal_xccdf_results.xml
```

Workspace default baseline per `stig_id` (explicit `baseline_id` on create/import always wins):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_collections/COLLECTION_ID/baseline_defaults" \
  -H "Content-Type: application/json" \
  -d '{"stig_id":"Example_STIG","baseline_id":"BASELINE_KV_KEY"}'
```

Assign a baseline to a host (idempotent — repeats return **200** with `"created": false`):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_hosts/HOST_ID/stigs" \
  -H "Content-Type: application/json" \
  -d '{"baseline_id":"BASELINE_KV_KEY"}'

# Or resolve revision from workspace default / catalog:
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_hosts/HOST_ID/stigs" \
  -H "Content-Type: application/json" \
  -d '{"stig_id":"Example_STIG"}'
```

The **STIG Editor** shows **Assign STIG** when you pick a host (baseline picker or `stig_id`).

After importing a **newer Manual STIG revision** (same `stig_id`), upgrade checklists explicitly so unchanged rules keep assessor state (`check_content_hash` merge):

```bash
# One host checklist
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_checklists/CHECKLIST_ID/upgrade" \
  -H "Content-Type: application/json" \
  -d '{"baseline_id":"NEW_BASELINE_KV_KEY"}'

# All checklists in a workspace still on the old revision
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_collections/COLLECTION_ID/upgrade_checklists" \
  -H "Content-Type: application/json" \
  -d '{"baseline_id":"NEW_BASELINE_KV_KEY","from_baseline_id":"OLD_BASELINE_KV_KEY"}'
```

The STIG Editor also exposes **Upgrade revision** when a host is selected (confirmation dialog; only baselines newer than the current revision).

Upgrade is **not atomic** across KV rows—if a request fails mid-way, re-run the same upgrade after resolving the error.

Reconcile indexed findings into KV (same job as the 5-minute saved search):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports/reconcile?earliest=-15m"
```

End-to-end RHEL 8 demo: `scripts/demo_rhel8_web01.py` (requires `SPLUNK_PASSWORD`).

## Tests

Offline:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
./scripts/validate_cklb.py ~/Downloads/*.cklb   # STIG Viewer CKLB shape
```

Splunk integration (built app mounted or installed):

```bash
export SPLUNK_PASSWORD='your-admin-password'
./scripts/run_splunk_tests.sh
```

## Search

Use `| inputlookup stig_reviews` (and related stanzas in `package/default/transforms.conf`) with app context **stigs_in_splunk**. See spec.md §12.

## Collection metrics and findings report

SplunkUI **Collection dashboard** (`stig_collection_dashboard_ui`) shows workspace-scoped review metrics, an open-findings report with CSV export, aggregated findings by group/rule/CCI, unreviewed rules/assets reports, and POA&M CSV/XLSX export.

REST (requires `stig_read` and workspace access):

- `GET /stig_collections/{id}/metrics` — counts by review status and severity, plus completion summary.
- `GET /stig_collections/{id}/findings` — paginated findings (default `status=open`; optional `severity`, `host_id`, `limit`, `offset`).
- `GET /stig_collections/{id}/findings/aggregate` — governance-open finding counts by `group_id`, `rule_id`, and CCI (from baseline rules).
- `GET /stig_collections/{id}/unreviewed/assets` — per-host unreviewed (`status=not_reviewed`) counts with per-baseline breakdown. Ignores findings `status` query params.
- `GET /stig_collections/{id}/unreviewed/rules` — per-rule unreviewed counts with host coverage. Same filter scope as assets (no `status` param).
- `GET /stig_collections/{id}/poam?format=json|csv|xlsx` — POA&M-style export template for governance-open findings (JSON includes example SPL alternative).
- `GET /stig_findings?stig_collection_id={id}` — same findings payload as the collection subpath.

For ad-hoc Splunk exports without REST, pipe open findings to `| outputcsv` after the governance filter in spec.md §12 (`status=open NOT workflow_state=accepted`).

See spec.md §11.6 for query parameters and response fields.
