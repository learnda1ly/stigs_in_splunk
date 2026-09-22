# STIG in Splunk — Build specification (PoC)

This document is the **authoritative requirements spec** for the Splunk app **`stigs_in_splunk`**. It is written so an AI agent (or engineer) can **implement the app from scratch** without inferring behavior from the existing repo.

**Product goal:** Store DISA STIG **baseline** content and per-host **checklist review state** (assessor findings) in the Splunk **KV store**, exposed only through a **custom REST API** (clients must not depend on raw KV REST for business logic).

**Splunk version target:** Enterprise **10.x** (developed against 10.2.x). Python **3.9** inside the app persist handler.

---

## 1. Scope

### 1.1 In scope (Phase 1 — PoC, must implement)

| Area | Requirement |
|------|-------------|
| Persistence | Six KV collections in `default/collections.conf` with `enforceTypes = true`. |
| API | Custom persist-conn REST handler; JSON for CRUD; raw XML/JSON for import/export bodies. |
| Baselines | Import from **XCCDF** (primary), **CKLB**, **CKL**; **deduplicate** identical revisions; multiple **revisions** allowed. |
| Checklists | Create checklist = one host + one baseline + workspace; spawn one **review** per baseline rule. |
| Export | Synthesize **CKLB** (JSON) and **CKL** (XML) from KV rows (no stored CKL/CKLB files). |
| ACL | Workspace access via **`stig_collection_grants`** (owner/manager/member/restricted + optional host/baseline ACL) and legacy **`access_principals`**, plus Splunk capabilities **`stig_read`**, **`stig_write`**, **`stig_admin`**. |
| Audit | Structured app logging for mutations (username + action + entity id). |
| Packaging | Reproducible builds with [Splunk UCC](https://splunk.github.io/addonfactory-ucc-generator/) (`ucc-gen build` / `package`). |
| Configuration UI | UCC-generated **Configuration** page: workspaces, baseline import/delete, editor/ingest settings. |
| Editor UX | SplunkUI React pages for checklist **edit**, **import** (CKL/CKLB), and **export**. |
| Dev UX | Bind-mount **built** app; vendored **Splunk Python SDK** at repo `lib/` for external tests/scripts only. |
| Tests | Offline unit tests (parsers, fingerprint); optional Splunk integration tests (REST + KV). |
| Search | KV lookups in `package/default/transforms.conf` so **`inputlookup`** works in Splunk Search (not raw KV REST in SPL). |

### 1.2 Out of scope (Phase 2 — do not build in PoC)

- Custom SplunkUI **settings** page (use the UCC Configuration page).
- Search macros, CIM Vulnerability datamodel, eventtypes for ingested STIG events.
- Full audit **dashboard** (logs only in PoC).
- XCCDF **results** import mapping to review status (pass/fail → open/not_a_finding).
- ~~Review **merge** across STIG revisions when `check_content_hash` matches~~ **implemented** — see §11.4 `upgrade` endpoints.
- ~~Cascading delete of hosts/checklists when a **stig_collection** is deleted~~ **implemented** — see §11.1 `DELETE` with `?cascade=true`.
- Baseline ACL per workspace (baselines are **global** in PoC).

---

## 2. Glossary

| Term | Meaning |
|------|---------|
| **stig_collection** | A **workspace**: a logical group of hosts and checklists with its own `access_principals`. Do **not** call this “collection” alone — that term means a Splunk **KV collection** stanza. |
| **host** | An assessed asset (device), scoped to exactly one `stig_collection`. |
| **baseline** | Immutable STIG **reference content** for one **revision** (metadata + rules), usually imported from XCCDF/CKLB/CKL. |
| **baseline rule** | One STIG rule row belonging to a baseline (`stig_baseline_rules`). |
| **checklist** | Binding of **one host + one baseline** within a workspace, plus CKLB-shaped **target_data**. |
| **review** | Per-rule **assessor state** for a checklist (`status`, `finding_details`, `comments`). Stored in `stig_reviews`. |
| **finding** | Compliance sense: a review with **`status == open`**. Not a separate entity. |
| **KV collection** | Stanza name in `collections.conf` (e.g. `stig_reviews`). |

---

## 3. Architecture

### 3.1 Entity relationships

```text
stig_collection ──< stig_host
stig_collection ──< stig_checklist >── stig_baseline (global, not FK to workspace)
stig_baseline   ──< stig_baseline_rule
stig_checklist  ──< stig_review
```

**Checklist create:** Insert one `stig_checklist` row, then batch-insert one `stig_review` per `stig_baseline_rule` for that baseline, each with `status = not_reviewed`.

**Checklist delete:** Delete all reviews with that `checklist_id`, then delete the checklist.

**Review identity (for future merge):** `group_id`, `rule_id`, `rule_version`, `check_content_hash` copied from the baseline rule at checklist creation.

### 3.2 Request flow

```text
Client (curl / SDK / Splunk Web)
  → HTTPS :8089 /servicesNS/nobody/stigs_in_splunk/stig_*
  → restmap.conf → persist handler (stig_rest_handler.py)
  → services/*.py (business logic + ACL)
  → kv_client.py → splunk.rest (in Splunk) OR splunklib (external tests)
  → KV store collections
```

**Rule:** External API consumers use **`/stig_*` custom REST only**. Direct `storage/collections/data/...` is for the app internals and admin debugging.

### 3.3 Dual KV client (required)

| Runtime | Backend | Notes |
|---------|---------|--------|
| Inside Splunk persist handler | `splunk.rest.simpleRequest` | Must **not** import vendored `splunklib` in the handler process (OpenSSL / Python mismatch on Splunk 10). |
| External Python (tests, scripts) | Vendored `splunklib` under `lib/` via `bin/_sdk_path.py` | Connect with session token or username/password. |

`kv_client.connect(session_key)` picks the backend automatically (`import splunk.rest` succeeds only in-app).

### 3.4 KV insert rules (critical)

1. **Never POST a client-supplied `_key`** on insert. Splunk KV generates `_key`; client keys caused 404 on read-back.
2. **`insert_record`:** strip `_key` from body, POST, read back by server-returned key, return full document.
3. **`new_id()`:** `uuid.uuid4().hex` (32 hex chars, **no dashes**) — acceptable for client-side correlation before insert, but prefer server `_key` after insert.
4. JSON array fields (`access_principals`, `ccis`, `target_data`, `metadata`) stored as **JSON strings** in KV.

---

## 4. Repository layout (UCC)

**Source of truth** is `package/` plus repo-root UCC files. **Installable artifact** is `output/stigs_in_splunk/` (or `output/stigs_in_splunk-<version>.tar.gz`).

```text
globalConfig.yaml          # UCC meta + pages.configuration (workspaces, baselines, settings)
additional_packaging.py    # post-build hooks (KV reload trigger, prune unused UCC stubs)
package/
  app.manifest
  README.txt
  static/                  # app icons (Splunkbase)
  LICENSES/
  metadata/default.meta
  default/                 # hand-authored .conf (NOT app.conf — UCC generates that)
    authorize.conf
    collections.conf
    restmap.conf
    web.conf
    transforms.conf
  bin/                     # persist REST + business logic (same module tree as before)
  lib/                     # requirements.txt: splunktaucclib (>=6.6.0,<8) + solnlib (<8) for UCC Configuration REST
output/                    # gitignored; ucc-gen build output
.venv-ucc/                 # local ucc-gen venv (gitignored)
lib/                       # repo-root vendored splunk-sdk for tests only (not shipped)
scripts/
  build_ucc.sh
  package_ucc.sh
  link-splunk-app.sh       # bind-mount output/stigs_in_splunk
  vendor_splunk_sdk.sh
  run_splunk_tests.sh
  demo_rhel8_web01.py
tests/
requirements.txt           # pin for vendor_splunk_sdk.sh
README.md
spec.md
```

**App identity:** `package.id = stigs_in_splunk`, label “STIG in Splunk”, version from `globalConfig.yaml` / `--ta-version` (default `0.1.0`).

### 4.1 UCC packaging pattern

- **`globalConfig.yaml`** defines `meta` and **`pages.configuration`** (no `pages.inputs`). This is a REST + KV app with a UCC Configuration UI, not a modular-input TA.
- UCC **generates** `default/app.conf`, `app.manifest` version fields, `VERSION`, the **Configuration** view (`configuration.xml`), REST handlers for configuration tabs, and copies `package/**` into `output/<app>/`.
- Hand-written `restmap.conf` / `web.conf` in `package/default/` stay for persist-conn `/stig_*` APIs. UCC **merges** additional restmap/web stanzas for Configuration endpoints (`[admin:stigs_in_splunk]` / `admin_external`). Never replace the built `restmap.conf` with the persist-only package file; `additional_packaging.py` restores the UCC stanzas if they are missing. Without them the Configuration page 404s.
- **`package/lib/requirements.txt`** must list `splunktaucclib>=6.6.0,<8` and `solnlib>=5.5.0,<8`. UCC pip-installs them into `output/<app>/lib`. Without `splunktaucclib`, Configuration REST handlers crash and Splunk Web shows `Unable to xml-parse the following data: %s`. Do not use solnlib 8.x (grpcio/OpenTelemetry wheels do not match Splunk's Python).
- **`additional_packaging.py`:** append `[triggers] reload.collections = simple` (and `reload.nav`); **keep** UCC `configuration.xml`; delete unused `inputs.xml` / `dashboard.xml` / `_redirect.xml`; restore `package/default/data/ui/nav/default.xml` so Editor / Import / Export remain the default views and **Configuration** is the UCC page.

### 4.3 Configuration page (required)

The Splunk Web **Configuration** view is the UCC-generated page (`/app/stigs_in_splunk/configuration`). Do **not** ship a parallel SplunkUI settings dashboard.

| Tab | UCC type | Storage | Handler |
|-----|----------|---------|---------|
| **Workspaces** | table + entity (`name`, `description`, `access_principals`, `is_default`) | KV `stig_collections` | `stig_ucc_workspace_rh.WorkspaceRestHandler` (lists **all** KV workspaces). A **Default** workspace is created if missing. Checklist imports with no workspace go there until the host is moved. Persist `/stig_collections` still filters by `access_principals` for the editor. |
| **Baselines** | table + delete (no file upload) | KV `stig_baselines` + `stig_baseline_rules` | `stig_ucc_baseline_rh.BaselineRestHandler`. **Do not** put a UCC file widget here — EAI XML cannot carry a library zip. Drop the DISA zip on **Import**; persist `/stig_baselines/jobs` chunks it and imports every `*Manual-xccdf.xml`. SRGs/SCAP skipped. Dedup by fingerprint; delete from this table. |
| **Editor & ingest** | settings form (no table) | `stigs_in_splunk_settings.conf` stanza `[general]` | UCC-generated MultipleModel handler |

**HEC token:** never an entity on Configuration. Token is read server-side from the `stig_findings` HTTP Event Collector input (`services/hec.py`).

**Editor vim toggle:** the React editor may still `GET`/`PATCH` `/stig_settings` as a JSON adapter over `[general]`. That adapter must not accept or return `hec_token`.

#### 4.3.1 App settings (`stigs_in_splunk_settings.conf` / `stig_settings`)

STIG Manager’s `/op/configuration` maps to Splunk **UCC Configuration → Editor & ingest** plus persist **`/stig_settings`**. There is no separate app-settings KV collection in normal deployments; values live in **`local/stigs_in_splunk_settings.conf`** stanza **`[general]`** (UCC-generated handler `stigs_in_splunk_rh_settings.py`). If that stanza is missing (legacy PoC), `services/settings.py` falls back to KV **`stig_editor_settings`** on read/write.

| Field | Type | Default | Who can change | Purpose |
|-------|------|---------|----------------|---------|
| `vim_mode` | bool | `false` | **UCC:** Splunk users with **write** on app configuration (`admin` / `sc_admin` per `metadata/default.meta`). **REST:** any user with **`stig_write`** (`POST`/`PATCH`/`PUT` `/stig_settings`; editor sends `vim_mode` only). | Enable vim-style keyboard layers in the STIG Editor (INSERT / field NORMAL / NAV). Per-browser badge can override until reload. |
| `trust_event_collection_id` | bool | `false` | UCC (admins) or **`stig_write`** via `/stig_settings` | When **false** (default), HEC ingest resolves workspace via assignment rules, host×baseline overrides, then Default. When **true**, honor `collectionId` on the event **before** rules (legacy Watcher senders). See [watcher-hec.md](docs/watcher-hec.md). |
| `ingest_index` | string | `stig` | UCC or **`stig_write`** | Target index for `stig:finding` events emitted by checklist import and server-side HEC posts (`services/hec.py`). |
| `ingest_sourcetype` | string | `stig:finding` | UCC or **`stig_write`** | Sourcetype for those events; must match the `stig_findings` HEC input and the scheduled reconcile search. |
| `hec_url` | string | `https://localhost:8088/services/collector/event` | UCC or **`stig_write`** | Server-side HEC collector URL used when applying imports (not exposed to browsers as a secret channel). |
| `reconcile_earliest` | string | `-15m` | UCC or **`stig_write`** | SPL earliest time for `| stigkvreconcile` and `GET|POST /stig_imports/reconcile` (relative or absolute). Saved search **STIG reconcile findings to KV** also sets `dispatch.earliest_time = -15m`; align both when changing the window. |

**Intentionally excluded (never stored in app settings):**

| Field | Where it lives |
|-------|----------------|
| `hec_token` | Splunk HTTP Event Collector input stanza **`[http://stig_findings]`** in `inputs.conf` (read server-side by `services/hec.py::lookup_hec_token`). Never returned from `/stig_settings`, never written from REST bodies (stripped in `save_settings`). |

**UCC admin REST (Configuration UI backend):** `GET|POST /servicesNS/nobody/stigs_in_splunk/stigs_in_splunk_settings/general` (Splunk Web proxies `stigs_in_splunk_settings` per `web.conf`). Field definitions and help text are authored in **`globalConfig.yaml`** tab `general`.

**Workspace names** are unique (case-insensitive). The UCC table row id is the workspace `name`. Baseline table row id is `ucc_name` (set on import; falls back to `_key` for legacy rows).

Do not upload a DISA library zip through the UCC file widget. Splunk wraps that file in EAI XML **before** the Python handler runs, so a 360MB–1GB zip fails with `Unable to xml-parse` (row id such as `July_2026`). Configuration Baselines is list/delete only. The Import page chunk-uploads the zip to persist `/stig_baselines/jobs` (4MB JSON chunks, staged under `$SPLUNK_HOME/var/run/stigs_in_splunk/baseline_jobs/`, max 2GB) and **imports every Manual-xccdf automatically**. Never send the zip through an EAI/`admin_external` handler.

### 4.2 Build commands

```bash
python3 -m venv .venv-ucc
.venv-ucc/bin/pip install -r requirements-ucc.txt
./scripts/build_ucc.sh
./scripts/package_ucc.sh    # optional .tar.gz for Splunk Web install
```

Use `--python-binary-name` pointing at `.venv-ucc/bin/python` (build script sets this) so `pip` is not invoked on the system Python.

---

## 5. Deployment and development

### 5.1 Install steps

1. **Build:** `./scripts/build_ucc.sh` → `output/stigs_in_splunk/`.
2. **Install on Splunk:** extract tarball to `$SPLUNK_HOME/etc/apps/` **or** `./scripts/link-splunk-app.sh` (bind-mounts `output/stigs_in_splunk`; Splunk 10 often **ignores symlinks**).
3. **Restart Splunk** after `package/default/*.conf` or `package/bin/**` changes (re-run build before restart when using mount).
4. Optional tests: `./scripts/vendor_splunk_sdk.sh` → repo `lib/splunklib` (not bundled in UCC output unless `package/lib/requirements.txt` lists `splunk-sdk`).
5. Reload transforms after `transforms.conf` change:  
   `POST /servicesNS/nobody/stigs_in_splunk/admin/conf-transforms/_reload`

### 5.2 Roles and capabilities

Define in `package/default/authorize.conf`:

| Capability | Meaning |
|------------|---------|
| `stig_read` | GET via custom REST |
| `stig_write` | POST / PATCH / PUT |
| `stig_admin` | DELETE; manage `access_principals` on workspaces (owners may also edit principals via grants) |

**Grant roles** (KV `stig_collection_grants`, REST `/stig_collections/{id}/grants`):

| Role | Read workspace | Write hosts/checklists/reviews | Manage grants | Edit workspace fields | Edit `access_principals` |
|------|----------------|--------------------------------|---------------|----------------------|---------------------------|
| **owner** | yes | yes (no `stig_write` required) | yes | yes | yes |
| **manager** | yes | yes (no `stig_write` required) | yes | yes | no |
| **member** | yes | requires **`stig_write`** | no | no | no |
| **restricted** | yes (ACL-filtered rows) | requires **`stig_write`** + ACL scope | no | no | no |

Legacy: principals listed in `access_principals` with no matching grant row behave as **member**. Empty `access_principals` ⇒ any user with STIG caps may read. Creating a grant syncs the principal into `access_principals` for backward-compatible readers.

**ACL:** optional `acl_host_ids`, `acl_baseline_ids`, and `acl_labels` JSON arrays on a grant. An empty array `[]` (or omitted field) means **no filter** for that dimension. When multiple dimensions are set, they compose as **AND** (host id, baseline id, and label intersection must all pass). Label ACL requires the host’s `label_ids` to intersect the grant’s `acl_labels`. Host `label_ids` and grant `acl_labels` must reference `stig_labels._key` rows in the same workspace.

Roles:

- **`stig_user`:** `stig_read`, `stig_write`
- **`stig_admin`:** inherits `stig_user`, plus `stig_admin`
- **`role_admin`:** enable all three for PoC admin UX

Map capabilities to HTTP methods in **each** `restmap.conf` stanza (see §7).

### 5.3 REST base URL

```text
https://<host>:8089/servicesNS/nobody/stigs_in_splunk
```

Resources: `stig_collections`, `stig_collection_grants` (nested under collections), `stig_hosts`, `stig_baselines`, `stig_checklists`, `stig_reviews`, `stig_imports`, `stig_settings` (§4.3.1, §11.7).

Authentication: Splunk session or Basic Auth (`-u user:pass`). TLS verify often disabled in dev (`curl -k`).

---

## 6. Splunk configuration (detailed)

### 6.1 `default/collections.conf`

Six stanzas: `stig_collections`, `stig_hosts`, `stig_baselines`, `stig_baseline_rules`, `stig_checklists`, `stig_reviews`.

All: `enforceTypes = true`.

**Accelerated fields (for KV queries):**

| Collection | Accelerated index |
|------------|-------------------|
| `stig_hosts` | `{"stig_collection_id": 1}` |
| `stig_baselines` | `{"content_fingerprint": 1}` |
| `stig_baseline_rules` | `{"baseline_id": 1, "group_id": 1}` |
| `stig_checklists` | `{"stig_collection_id": 1}` |
| `stig_reviews` | `{"checklist_id": 1, "status": 1}` |

**`default/app.conf`:** include `[triggers] reload.collections = simple`.

### 6.2 `default/restmap.conf`

**Critical Splunk constraint:** only **one** `match =` per stanza; duplicate `match` keys in one stanza **overwrite** — only the last survives.

Implement **five separate stanzas**, one per top-level resource path:

- `[script:stig_api_collections]` → `match = /stig_collections`
- `[script:stig_api_hosts]` → `match = /stig_hosts`
- `[script:stig_api_baselines]` → `match = /stig_baselines`
- `[script:stig_api_checklists]` → `match = /stig_checklists`
- `[script:stig_api_reviews]` → `match = /stig_reviews`

Shared settings per stanza:

```ini
script = stig_rest_handler.py
scripttype = persist
handler = stig_rest_handler.StigRestHandler
python.version = python3
requireAuthentication = true
output_modes = json
passPayload = true
passSession = true
passHttpHeaders = true
methods = GET,POST,PATCH,PUT,DELETE
capability.stig_read = GET
capability.stig_write = POST|PATCH|PUT
capability.stig_admin = DELETE
```

Sub-paths (`import`, `export`, `rules`) are routed inside the handler by parsing `rest_path` after the resource name.

### 6.3 `default/web.conf`

Expose endpoints to Splunk Web / management port using **glob patterns** (not regex):

- For each resource: `[expose:stig_*]` with `pattern = stig_*` and `pattern = stig_*/**` for nested paths (`import`, `export`, `{id}/rules`).

Methods: `GET,POST,PATCH,PUT,DELETE` on each expose stanza.

### 6.4 `default/transforms.conf`

Define **kvstore external lookups** for Search (required — see §12):

```ini
[stig_reviews]
external_type = kvstore
collection = stig_reviews
fields_list = _key, checklist_id, baseline_id, group_id, rule_id, rule_version, check_content_hash, status, finding_details, comments, updated_at, updated_by

[stig_checklists]
external_type = kvstore
collection = stig_checklists
fields_list = _key, stig_collection_id, host_id, baseline_id, title, mode, target_data, created_at, updated_at, created_by, updated_by

[stig_baseline_rules]
external_type = kvstore
collection = stig_baseline_rules
fields_list = _key, baseline_id, group_id, rule_id, rule_id_src, rule_version, severity, rule_title, group_title, check_content_hash

[stig_baselines]
external_type = kvstore
collection = stig_baselines
fields_list = _key, stig_id, title, version, rule_count, content_fingerprint, source_uri, imported_at
```

(Add other collections if reporting needs them.)

---

## 7. KV schemas

Foreign keys are string `_key` values unless noted. Timestamps are **epoch seconds** (float).

### 7.1 `stig_collections`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | Server-generated |
| `name` | string | Required on create |
| `description` | string | Optional |
| `metadata` | string | Optional JSON object string for arbitrary workspace key/value metadata (REST `GET/PATCH .../metadata`). |
| `access_principals` | string | JSON array string, e.g. `["user:alice","role:stig_admin"]`. Empty/missing ⇒ readable by all authenticated users with caps. |
| `is_default` | bool | Exactly one workspace is the import default. Checklist ingest with no `stig_collection_id` / `collectionId` uses it. |
| `created_at`, `updated_at` | time | |
| `created_by`, `updated_by` | string | Splunk username |

### 7.1a `stig_collection_grants`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | Grant id |
| `stig_collection_id` | string | FK → workspace |
| `principal` | string | `user:<name>` or `role:<name>` |
| `grant_role` | string | `owner` \| `manager` \| `member` \| `restricted` |
| `acl_host_ids` | string | JSON array of `stig_hosts._key`; empty ⇒ no host filter |
| `acl_baseline_ids` | string | JSON array of `stig_baselines._key`; empty ⇒ no baseline filter |
| `acl_labels` | string | JSON array of `stig_labels._key`; empty ⇒ no label filter |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

### 7.2 `stig_hosts`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | |
| `stig_collection_id` | string | FK → workspace |
| `hostname`, `ip_address`, `fqdn`, `mac_address` | string | CKL/CKLB target |
| `role`, `asset_type`, `tech_area` | string | Defaults: `role=None`, `asset_type=Computing` |
| `web_or_database` | bool | Default false |
| `metadata` | string | JSON object string |
| `label_ids` | string | JSON array of `stig_labels._key` in the same workspace |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

### 7.2a `stig_labels`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | Label id |
| `stig_collection_id` | string | FK → workspace |
| `name` | string | Display name |
| `color` | string | Optional UI color token |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

REST: `GET/POST /stig_collections/{id}/labels`, `GET/PATCH/DELETE .../labels/{labelId}`, `POST .../labels/{labelId}/assets` with `{host_ids:[]}`.

### 7.3 `stig_baselines`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | |
| `stig_id` | string | e.g. `STIG`, `RHEL_8_STIG` |
| `title`, `stig_name` | string | |
| `version`, `release_info`, `benchmark_date` | string | Revision metadata |
| `xccdf_benchmark_id` | string | XCCDF Benchmark `@id` |
| `rule_count` | number | Count at import |
| `source_type` | string | `xccdf` \| `cklb` \| `ckl` |
| `source_uri` | string | Filename/URL hint from client |
| `ucc_name` | string | Unique id for the UCC Configuration table row |
| `content_fingerprint` | string | SHA-256 hex; dedup key (§9) |
| `imported_at` | time | |
| `imported_by` | string | |

**Baselines are global:** not scoped to `stig_collection`. Any user with REST caps can list/import.

### 7.4 `stig_baseline_rules`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | |
| `baseline_id` | string | FK |
| `group_id` | string | V-id (may be empty in some XCCDF if only SV- in `ident`) |
| `rule_id` | string | SV-id |
| `rule_id_src` | string | XCCDF Rule `@id` |
| `rule_version` | string | DISA rule version (e.g. `RHEL-08-010000`) |
| `severity` | string | `high` \| `medium` \| `low` |
| `rule_title`, `discussion`, `check_content`, `fix_text` | string | |
| `ccis` | string | JSON array string |
| `check_content_hash` | string | SHA-256 of normalized check text |
| `group_title` | string | From XCCDF Group title |

### 7.5 `stig_checklists`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | Used as CKLB export id |
| `stig_collection_id`, `host_id`, `baseline_id` | string | FKs |
| `title` | string | |
| `mode` | number | CKLB default `1` |
| `target_data` | string | JSON; CKLB `target_data` shape |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

### 7.6 `stig_reviews`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | |
| `checklist_id`, `baseline_id` | string | FK |
| `group_id`, `rule_id`, `rule_version` | string | |
| `check_content_hash` | string | Snapshot from baseline rule |
| `status` | string | See §10 |
| `finding_details`, `comments` | string | |
| `ingest_lock` | bool | When **true**, HEC/reconcile must **not** overwrite this review. Default false; incoming is authoritative. |
| `workflow_state` | string | `draft` \| `submitted` \| `accepted` (reject returns to `draft`; see FEATURE_PARITY.md) |
| `submitted_at`, `submitted_by` | time / string | Set on submit |
| `accepted_at`, `accepted_by` | time / string | Set on accept |
| `rejected_at`, `rejected_by`, `reject_feedback` | | Set on reject (feedback optional) |
| `updated_at` | time | |
| `updated_by` | string | Set on every update |

---

## 8. Access control

### 8.1 Principals

`access_principals` entries:

- `user:<splunk_username>`
- `role:<splunk_role_name>`

Evaluation (`bin/access.py`):

- **`stig_admin`** capability, or roles **`admin`** / **`sc_admin`:** full access to all workspaces.
- **Read:** user matches a principal, OR list is empty (open read within cap holders).
- **Write:** must pass read, plus **`stig_write`** capability (admin bypass).
- **Accept/reject submitted reviews:** **`stig_admin`**, workspace grant role **owner** or **manager**, or a match on **`review_accept_principals`**. **`stig_review_accept`** does not imply accept on every readable workspace (use explicit principals or owner/manager grants).

### 8.2 Scope by entity

| Entity | ACL |
|--------|-----|
| `stig_collection` | Principals on record; list filtered for GET |
| `stig_host`, `stig_checklist`, `stig_review` | Via parent `stig_collection_id` |
| `stig_baseline`, `stig_baseline_rule` | **No workspace ACL** in PoC |

### 8.3 DELETE

Requires **`stig_admin`** (or admin role) for: `stig_collection`, `stig_host`, `stig_checklist`.

---

## 9. Baseline import and deduplication

### 9.1 Import endpoint

`POST /stig_baselines/import` (persist REST) **or** the UCC Configuration **Baselines** tab (file upload). Both call `services.baselines.import_baselines_payload`.

Query parameters (must support Splunk persist **query as list of pairs** — normalize to dict in handler):

| Param | Default | Meaning |
|-------|---------|---------|
| `format` | `xccdf` | `xccdf` \| `cklb` \| `ckl` \| `zip` (`zip` or a body starting `PK` walks nested DISA zips) |
| `source_uri` | `""` | Stored on baseline; not used for dedup |

Body: raw document bytes (XML, JSON, or zip). Zip-of-zips: import every `*Manual-xccdf.xml` that is not an SRG or SCAP/OCIL file. CKL/CKLB inside the zip are ignored (those are checklists, not baselines).

A zip import returns `{imported, created, deduplicated, baselines:[...]}`. A single-file import still returns the baseline record (plus `deduplicated` when it was a no-op).

### 9.2 Deduplication policy

- **Multiple revisions** of a STIG (e.g. V2R6 vs V2R7) → **separate** baselines (allowed).
- **Same revision imported twice** → **no duplicate** rows; return existing baseline.

### 9.3 `content_fingerprint` algorithm

Compute after parse, before insert:

1. **Revision object** (case/normalization):
   - `stig_id`: strip, casefold
   - `version`, `benchmark_date`, `xccdf_benchmark_id`: strip
   - `release_info`: whitespace-normalized like check content
2. **Rules array:** sort by `(group_id, rule_id, rule_version)`; for each rule include  
   `{group_id, rule_id, rule_version, check_content_hash}`.
3. `canonical = json.dumps({"revision": ..., "rules": ...}, sort_keys=True, separators=(",", ":"))`
4. `content_fingerprint = sha256(canonical).hexdigest()`

On import:

1. Query `stig_baselines` where `content_fingerprint == <hash>` (use accelerated field).
2. If found: audit `import_deduplicated`; return **`200`** JSON with existing record + **`"deduplicated": true`**.
3. If not found: insert baseline + all rules; audit `import`; return **`201`**.

**Legacy rows** imported before `content_fingerprint` existed are not deduplicated until re-imported once (first re-import stores fingerprint; subsequent imports dedupe).

### 9.4 XCCDF parsing (DISA / XCCDF 1.1)

Implement namespace-agnostic parsing (`{*}` in ElementTree):

- Locate `Benchmark` (root or descendant).
- Metadata: `title`, `version`, `status/@date`, `plain-text` id `release-info`, `@id` → `xccdf_benchmark_id`.
- Walk document order: on `Group`, capture `title` → `group_title`; on `Rule`, extract fields.
- **Idents:** CCI (system contains `cci`), `V-*` → `group_id`, `SV-*` → `rule_id`, else rule version; fallback `Rule/@id` → `rule_id_src` / `rule_id`.
- Check content: nested `check` / `check-content`, else direct `check-content` child.
- `@severity` → lowercase severity.
- `check_content_hash` via normalized whitespace SHA-256.

**Validated scale:** DISA RHEL 8 V2R6 Manual STIG ≈ **366** rules per baseline.

### 9.5 CKLB / CKL baseline import

- **CKLB:** JSON; first element of `stigs[]`; map `rules[]` to same internal rule shape.
- **CKL:** XML; STIG_INFO + VULN/STIG_DATA maps; map vulnerability fields to rule shape.

---

## 10. Status and export mappings

### 10.1 Canonical review status (KV)

| Internal | CKLB | CKL (v2.2) |
|----------|------|------------|
| `not_reviewed` | `not_reviewed` | `Not_Reviewed` |
| `open` | `open` | `Open` |
| `not_a_finding` | `not_a_finding` | `NotAFinding` |
| `not_applicable` | `not_applicable` | `Not_Applicable` |

Baseline import does **not** set review status (checklist create sets `not_reviewed`).

### 10.2 Export

`GET /stig_checklists/{id}/export?format=cklb|ckl`

- Join checklist + host + baseline metadata + baseline rules + reviews.
- Match reviews to rules primarily by `group_id` (PoC).
- Response: JSON string (CKLB) or XML string (CKL); appropriate `Content-Type`.

---

## 11. REST API reference

**Handler behavior:**

- Parse `rest_path` → `(resource, parts)`.
- **`_normalize_query`:** Splunk may send `query` as `[["k","v"],...]` — convert to dict.
- **`session`:** must include `authtoken`; use for `kv_client.connect`.
- **`session.capabilities`:** treat as dict; if missing, use `{}`.
- JSON responses: `{"payload": "<json string>", "status": N, "headers": [("Content-Type", "application/json")]}`.
- Errors: JSON `{"error": "<message>"}` with 4xx/5xx.
- Log stack traces on 500; do not leak stack to client.

### 11.1 `stig_collections`

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/stig_collections` | — | Array of workspaces user can read. Ensures a Default workspace exists. |
| POST | `/stig_collections` | JSON `{name, description?, access_principals?, is_default?}` | **201** created record |
| GET | `/stig_collections/{id}` | — | Record or **404** |
| PATCH/PUT | `/stig_collections/{id}` | Partial JSON | Updated record. Setting `is_default` true unsets the previous default. |
| DELETE | `/stig_collections/{id}` | Query `cascade=true` or JSON `{"cascade": true}` when the workspace has dependent rows | `{deleted, cascade, removed}`; requires **stig_admin**. Cannot delete the default workspace. Without `cascade`, **409** when hosts, checklists, reviews, grants, or assignment rows remain (audit `delete_blocked`). Response `children` is **per-type** counts (reviews may overlap checklists; do not sum all keys for a deduplicated total). With `cascade=true`, removes workspace-scoped hosts, checklists, reviews, grants, and assignment rules/overrides; **global baselines are untouched**. Empty workspaces delete without `cascade`. |
| GET | `/stig_collections/{id}/metrics` | — | Workspace metrics: `totals`, `completion`, `by_status`, `by_severity`, `open_by_severity`. Requires **stig_read** and workspace access (**404** if hidden). |
| GET | `/stig_collections/{id}/findings` | Query filters (see §11.6) | Paginated findings report for assessors. Default filter: `status=open`. |
| GET | `/stig_collections/{id}/findings/aggregate` | `group_by?`, filters (see §11.6) | Governance-open counts by group, rule, and/or CCI. |
| GET | `/stig_collections/{id}/unreviewed/assets` | Filters (see §11.6) | Per-host unreviewed counts (`status=not_reviewed`). |
| GET | `/stig_collections/{id}/unreviewed/rules` | Filters (see §11.6) | Per-rule unreviewed counts with hostnames. |
| GET | `/stig_collections/{id}/poam` | `format?` (`json`, `csv`, `xlsx`) | POA&M-style export for governance-open findings. |
| POST/PUT | `/stig_collections/{id}/archive/ckl` | Query or JSON `host_id?`, `baseline_id?` | Zip archive of all CKL checklists in the workspace (grant ACL applied). **400** when no checklists match. **404** when workspace hidden. Response JSON: `{filename, format, count, files, content_base64, stig_collection_id, filters}`. Zip entry names: `{hostname}_{stig_id}_{version}.ckl`. |
| POST/PUT | `/stig_collections/{id}/archive/cklb` | Same filters as CKL archive | Same as CKL archive with `.cklb` entries. |

Default `access_principals` on create: `["user:<creator>"]` if omitted. The Default holding workspace uses `[]` (any user with STIG caps).

`POST /stig_imports` may omit `stig_collection_id`; the Default workspace is used. Move a host with `POST /stig_hosts/{id}` `{stig_collection_id}` (checklists follow the host).

#### Grants (`/stig_collections/{id}/grants`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/stig_collections/{id}/grants` | — | Array of grant records (requires workspace read) |
| POST | `/stig_collections/{id}/grants` | `{principal, grant_role?, acl_host_ids?, acl_baseline_ids?, acl_labels?}` | **201**; requires **owner** or **manager** |
| GET | `/stig_collections/{id}/grants/{grantId}` | — | Grant or **404** |
| PATCH/PUT | `/stig_collections/{id}/grants/{grantId}` | Partial grant JSON | Updated grant |
| PUT/PATCH | `/stig_collections/{id}/grants/{grantId}/acl` | `{acl_host_ids?, acl_baseline_ids?, acl_labels?}` | Updated grant ACL fields only |
| DELETE | `/stig_collections/{id}/grants/{grantId}` | — | `{deleted: grantId}` |

`principal` must be `user:<name>` or `role:<name>`. `grant_role` is one of `owner`, `manager`, `member`, `restricted`.

### 11.2 `stig_hosts`

| Method | Path | Query | Body |
|--------|------|-------|------|
| GET | `/stig_hosts` | `stig_collection_id?` | — |
| POST | `/stig_hosts` | — | `{stig_collection_id, hostname, ip_address?, ...}` |
| GET | `/stig_hosts/{id}` | — | Host document |
| GET | `/stig_hosts/{id}/checklists` | — | Checklists for this host (respects grants/ACL) |
| POST | `/stig_hosts/{id}/stigs` | — | `{baseline_id}` **or** `{stig_id}` (workspace default / catalog resolution). Creates checklist + spawns reviews; **200** + `"created": false` when already assigned (idempotent). **201** + `"created": true` on first assign. |
| DELETE | `/stig_hosts/{id}/stigs/{baselineIdOrStigId}` | — | Removes **one** checklist: path segment is baseline KV `_key` **or** logical `stig_id` resolved like POST assign (workspace default → catalog). Does **not** delete other revision checklists for the same `stig_id`; pass each revision’s baseline `_key` to remove multiples. Requires workspace **write**. |
| PATCH/DELETE | `/stig_hosts/{id}` | — | PATCH fields optional; DELETE requires **stig_admin** |

DELETE requires **stig_admin**. Writes require workspace **stig_write** access.

### 11.3 `stig_baselines`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_baselines` | List all baseline headers |
| GET | `/stig_baselines/hierarchy` | Benchmark-centric library: groups catalog rows by `stig_id` with per-revision metadata (`version`, `release_info`, `content_fingerprint`, `rule_count`, `imported_at`, …) |
| GET | `/stig_baselines/by_stig/{stigId}` | One benchmark entry from hierarchy (404 when unknown) |
| GET | `/stig_baselines/rule/{ruleKey}` | Stable rule detail by KV `_key` on `stig_baseline_rules` (includes parent baseline summary) |
| GET | `/stig_baselines/{id}/rules/{ruleRef}` | Rule in baseline context. `ruleRef` may be the rule KV `_key`, composite `group_id\|rule_id` (V-id\|SV-id), or SV-id via `rule_id` / `rule_id_src`. A bare V-id is not accepted (avoids first-row scans). Optional query `group_id` disambiguates duplicate SV-ids in one baseline. Ambiguous matches return **404**. |
| POST | `/stig_baselines/import` | Query `format` (`xccdf` \| `cklb` \| `ckl` \| `zip`), `source_uri`; raw body. Zip walks nested archives and imports only `*Manual-xccdf.xml` STIG baselines. |
| GET | `/stig_baselines/{id}/rules` | All rules for baseline |
| DELETE | `/stig_baselines/{id}` | Remove baseline + rules (UCC Configuration table or persist REST). |

UCC Configuration **Baselines** tab is the management UI: list, import (including zip-of-zips), delete.

Import responses:

- **201** new baseline document (KV fields), or zip batch `{imported, created, deduplicated, baselines}`.
- **200** existing baseline + `"deduplicated": true` (single-file no-op).

### 11.4 `stig_checklists`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_checklists` | Query `stig_collection_id?` |
| POST | `/stig_checklists` | `{stig_collection_id, host_id, baseline_id?, stig_id?, title?, mode?, target_data?}` → spawns reviews. Duplicate host+baseline → **400**. Prefer **`POST /stig_hosts/{id}/stigs`** for idempotent assign. |
| GET/PATCH/DELETE | `/stig_checklists/{id}` | DELETE cascades reviews |
| GET | `/stig_checklists/{id}/export` | Query `format=cklb|ckl` |
| POST/PUT | `/stig_checklists/export_bulk` | JSON `{checklist_ids?, stig_collection_id?, format, host_id?, baseline_id?}` | Zip of multiple checklists. Either `checklist_ids` **or** `stig_collection_id` (workspace-scoped, optional host/baseline filters). Workspace-scoped calls use the same read ACL as archive export: missing or unreadable workspace → **404** (not **403**). **400** when filters match no checklists. Same zip/filename rules as collection archive. |
| POST/PUT | `/stig_checklists/{id}/upgrade` | `{baseline_id}` — same `stig_id`, newer revision; merge reviews when `check_content_hash` matches |
| POST | `/stig_imports` | Query `format=ckl\|cklb\|zip\|xccdf-results-zip\|xccdf-results`, `source_uri`, `stig_collection_id`; raw body (see §11.4.1) |
| POST | `/stig_collections/{id}/imports` | JSON `{files: [{source_uri, format?, content\|content_base64}]}` **or** raw zip body (`format=zip` query or PK magic). Batch CKL/CKLB/XCCDF-results collection import; workspace **write** required. |
| GET/POST/DELETE | `/stig_collections/{id}/baseline_defaults` | Workspace default `baseline_id` per `stig_id` (`default_baseline_map` on collection) |
| GET/PATCH | `/stig_collections/{id}/review_requirements` | Workspace review validation policy (`review_requirements` JSON on collection). **GET** returns `{stig_collection_id, review_requirements, defaults}`. **PATCH** body `{review_requirements: {...}}` or flat policy fields; requires workspace **write**. |
| GET/PATCH | `/stig_collections/{id}/metadata` | Optional workspace metadata (`metadata` JSON on collection). **GET** returns `{stig_collection_id, metadata}` (empty object when unset). **PATCH** requires workspace **write**; body `{metadata: {...}}` shallow-merges keys (set a key to JSON `null` to remove). `{replace: true, metadata: {...}}` replaces the entire object. `{clear: true}` removes all keys. Values must be JSON-serializable; non-object `metadata` returns **400**. |
| POST/PUT | `/stig_collections/{id}/upgrade_checklists` | `{baseline_id, from_baseline_id?, stig_id?}` — bulk upgrade matching checklists in workspace |

POST validates: host belongs to workspace; baseline exists; baseline has rules.

**Revision upgrade:** does not run automatically on baseline import. Call `upgrade` explicitly after importing a newer Manual STIG revision. The target baseline must be a **newer** DISA-style revision (`VxRy` compared numerically, else `imported_at` on the baseline row). For each rule in the target baseline, the prior review is matched by composite `(group_id, rule_id)` only. When `check_content_hash` is unchanged, assessor fields and `workflow_state` carry forward. When the hash changed and the row is editable draft (not `ingest_lock`, `workflow_state=draft`), `status` resets to `not_reviewed` and assessor text (`finding_details`, `comments`, `reject_feedback`) clears for re-assessment. Locked or submitted/accepted rows keep assessor content on hash mismatch (metadata still updates). Orphan reviews for removed rules are deleted; new rules spawn `not_reviewed` rows. Requires workspace **write** (same as checklist PATCH). Bulk upgrade calls `require_workspace_write` before listing targets (403 for read-only callers).

**Non-atomic upgrade:** reviews are updated one KV row at a time, then the checklist `baseline_id` is updated last. A mid-request KV failure can leave reviews on the new baseline while the checklist still references the old baseline (or the inverse). Re-run `upgrade` with the same target after fixing the error, or restore from backup; there is no multi-document transaction.

### 11.4.1 Checklist file import and HEC ingest

`POST /stig_imports` parses one `.ckl`, `.cklb`, zip archive (checklists and/or XCCDF results), or a single XCCDF `TestResult` scan file. CKL/CKLB use the same shape as [STIG Manager Watcher](https://github.com/NUWCDIVNPT/stigman-watcher) (`reviewsFromCkl` / `reviewsFromCklb`). XCCDF results map `rule-result@result` to Watcher `result` values (`pass`, `fail`, `notapplicable`, `notchecked`).

**Zip archives (`format=zip`):** nested zips supported; members are `.ckl`/`.cklb` and/or XCCDF result XML (`*-results.xml`, `*_results.xml`, or XML containing `TestResult` + `rule-result`). Manual STIG benchmark XML, SRG/SCAP source data streams, and OCIL are skipped. Caps: 500 members per archive, per-member and total uncompressed limits in `checklist_zip.py` / `xccdf_results_zip.py`. **`format=xccdf-results-zip`** accepts only XCCDF result members (errors when none). Mixed checklist + results archives are processed in one batch with per-file `ok`/`error` rows.

**Collection import builder:** `POST /stig_collections/{id}/imports` accepts JSON `files[]` (`ckl`, `cklb`, or `xccdf-results` per row) and returns `{stig_collection_id, results[], summary}`. Zip body uses the same walker as `format=zip`. HTTP status: **201** when `summary.created > 0` and `summary.failed == 0`; otherwise **200**. **Not supported:** full SCAP source data stream bundle parsing (only discrete OpenSCAP/Evaluate-STIG `TestResult` XML files in zip).

For all formats:

1. Emits one **fat** `stig:finding` JSON event per rule to **HEC** (`index=stig`, `sourcetype=stig:finding`). Each event includes Watcher review fields **and** asset `target_data`, STIG metadata, and the rule body (title, check content, fix text, CCIs, hashes) so a CKL/CKLB can be synthesized later from the index + KV.
2. Applies the same events to KV current state (host, baseline, checklist, reviews).

External Evaluate-STIG / Watcher streams must POST the same event shape to the HEC input `[http://stig_findings]`. Full field reference: [docs/watcher-hec.md](../docs/watcher-hec.md).

`GET|POST /stig_imports/reconcile` (and scheduled search `| stigkvreconcile`) reads recent index events and applies them to KV.

**Override policy:** a matching review is updated from the incoming event (authoritative) unless `ingest_lock` is true on the KV review. Incoming events never set `ingest_lock`.

Requires **`stig_write`**.

### 11.5 `stig_reviews`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_reviews` | Query `checklist_id?`, `status?`, `workflow_state?`, `stig_collection_id?`, `rule_id?`, `rule_version?`, `valid?` |
| GET | `/stig_reviews/{id}` | Single review |
| PATCH/PUT | `/stig_reviews/{id}` | `{status?, finding_details?, comments?, ingest_lock?}` |
| POST | `/stig_reviews/{id}/submit` | Assessor submit (`stig_write` + workspace grant); review must be valid |
| POST | `/stig_reviews/{id}/accept` | Owner/manager accept (`stig_review_accept`, grant role, or `review_accept_principals`) |
| POST | `/stig_reviews/{id}/reject` | `{reject_feedback?}` — returns review to `draft` |
| POST | `/stig_reviews/batch` | Field batch: `{reviews: [{_key, ...}]}` **or** governance: `{action, review_ids[], reject_feedback?}` (mutually exclusive; max 500 ids). Both return `{updated: [...], errors: [...], summary: {total, succeeded, failed}}`; governance adds `action`. |

Updates require workspace **write** access via parent checklist. Content PATCH is allowed only in `workflow_state=draft` (except `stig_admin`). Validate `status` against allowed set; accept internal or CKLB status strings on input. Content PATCH and submit enforce the workspace **`review_requirements`** policy (see below); invalid rows return **400** with a message derived from `validation_errors`. `ingest_lock=true` blocks HEC/reconcile from overwriting that finding. See **FEATURE_PARITY.md** for the state machine.

**Review requirements policy** (stored on `stig_collections.review_requirements` as JSON):

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `require_finding_details` | bool | `false` | Trimmed finding details required (min length below). |
| `require_comments` | bool | `false` | Trimmed comments required (min length below). |
| `min_finding_details_length` | int | `0` | Minimum trimmed length when `require_finding_details` is true (implicit minimum 1). |
| `min_comments_length` | int | `0` | Minimum trimmed length when `require_comments` is true (implicit minimum 1). |
| `applies_to_statuses` | string[] | `[]` | When empty, policy applies to all statuses; when set, only listed assessor statuses are validated. |

When both `require_*` flags are false and both minimums are zero, validation matches legacy behavior: at least one of finding details or comments must be non-empty after trim. A non-zero minimum length implicitly sets the corresponding `require_*` flag on persist (PATCH normalizes stored policy).

**Batch updates** apply each row independently (**partial success**). Response: `{updated: [...], errors: [{_key?, error, code?}], summary: {total, succeeded, failed}}`. Rows the caller cannot write return `code: forbidden`; missing keys return `not_found`. Maximum **500** reviews per request.

### 11.6 Metrics and findings report

**Unreviewed reports** (`/unreviewed/assets`, `/unreviewed/rules`) accept the same **scope** filters as findings (`host_id`, `hostname`, `baseline_id`, `rule_id`, `group_id`, `severity`) but **ignore `status`** (and findings-only params such as `limit` / `offset`). They always count rows with assessor **`status=not_reviewed`** only—do not copy findings query strings that default `status=open` or apply governance filters.

| Method | Path | Query | Response |
|--------|------|-------|----------|
| GET | `/stig_collections/{id}/metrics` | — | Aggregated counts from KV reviews (joined to baseline rules for severity). |
| GET | `/stig_collections/{id}/findings` | `status?` (comma-separated; default **open**), `severity?`, `host_id?`, `hostname?` (substring), `baseline_id?`, `rule_id?`, `limit?` (default **500**, max **2000**), `offset?` (default **0**) | `{findings: [...], pagination: {limit, offset, total, has_more}, filters}` |
| GET | `/stig_collections/{id}/findings/aggregate` | `group_by?` (comma-separated: `group_id`, `rule_id`, `cci`; default all three). Same filter query params as findings; default `status=open` with governance filter (open ∧ not accepted). | `{open_findings_total, by_group_id?, by_rule_id?, by_cci?, group_by, filters, scan_note}` — buckets include `count`, `host_count`, `hostnames`, `severity`; `by_group_id` / `by_rule_id` also include `baseline_id`, `stig_id`, `baseline_title` (rule IDs scoped per baseline). |
| GET | `/stig_collections/{id}/poam` | `format?` — `json` (default), `csv`, or `xlsx`. Same filter query params as findings. Default `status=open` with governance filter when status includes open. | **json:** `{rows, columns, row_count, splunk_alternative}` (`splunk_alternative` documents governance SPL + limitations vs enriched POA&M); **csv:** `text/csv` with `Content-Disposition` filename and `X-Stig-Row-Count`; **xlsx:** `{content_base64, filename, format, row_count}`. |
| GET | `/stig_collections/{id}/unreviewed/assets` | `host_id?`, `hostname?` (substring), `baseline_id?`, `rule_id?`, `group_id?`, `severity?` | `{definition, total_unreviewed, asset_count, assets: [{host_id, hostname, unreviewed_count, by_baseline: [{baseline_id, stig_id, baseline_title, unreviewed_count}]}], filters, splunk_alternative}` — only reviews with **status=not_reviewed**; ACL matches findings. |
| GET | `/stig_collections/{id}/unreviewed/rules` | Same query filters as unreviewed assets | `{definition, total_unreviewed, rule_count, rules: [{baseline_id, stig_id, group_id, rule_id, severity, rule_title?, unreviewed_count, host_count, hostnames}], filters, splunk_alternative}` — rule IDs scoped per baseline. |
| GET | `/stig_findings` | Same as collection findings; **`stig_collection_id` required** | Same body as `/stig_collections/{id}/findings` |

Each finding row includes: `hostname`, `host_id`, `baseline_id`, `baseline_title`, `stig_id`, `group_id`, `rule_id`, `rule_version`, `severity`, `status`, `finding_details`, `comments`, `valid`, `ingest_lock`, `updated_at`, `updated_by`, `checklist_id`, `_key`.

SplunkUI **Collection dashboard** (`stig_collection_dashboard_ui`) loads metrics, findings, **aggregated open findings** (by group, rule, CCI), **unreviewed** rules/assets reports, and **POA&M** CSV/XLSX export for governance-open rows. Optional Simple XML dashboard: `stig_collection_metrics_lookup`.

### 11.7 `stig_settings` (app configuration adapter)

JSON adapter over **`stigs_in_splunk_settings.conf`** `[general]` (see §4.3.1). STIG Manager migrators can treat this as the Splunk-shaped **`/op/configuration`** surface for editor + ingest (not workspace catalog).

| Method | Path | Capability | Body | Response |
|--------|------|------------|------|----------|
| GET | `/stig_settings` | **`stig_read`** | — | Public settings object (no `hec_token`). |
| POST / PATCH / PUT | `/stig_settings` | **`stig_write`** | Partial JSON; any §4.3.1 field except `hec_token` | Updated public object. Unmentioned fields are preserved. `hec_token` in the body is ignored. |

**GET response fields:** `_key` (always `general`), `vim_mode`, `trust_event_collection_id`, `ingest_index`, `ingest_sourcetype`, `hec_url`, `reconcile_earliest`, `updated_at`, `updated_by`. Missing conf values use defaults from `models.py`.

**Typical callers:** STIG Editor (`vim_mode` only), classic **Editor shortcuts** view, automation scripts with **`stig_write`**. Full-form edits should use the UCC **Configuration** page so Splunk audits conf changes.

---

## 12. Splunk Search (reporting)

**Do not** rely on `| rest .../storage/collections/data/...` for reviews: that endpoint returns a **flat JSON array**, not Splunk REST `entry[]`, so typical `rest` + `spath` patterns return **zero rows**.

**Do** use kvstore lookups from `transforms.conf` with app context **`stigs_in_splunk`**:

All review rows:

```spl
| inputlookup stig_reviews
| table _key checklist_id group_id rule_id status finding_details comments updated_at
```

Open findings only (assessor status):

```spl
| inputlookup stig_reviews
| search status=open
```

Open findings not yet accepted (governance):

```spl
| inputlookup stig_reviews
| search status=open NOT workflow_state=accepted
```

Unreviewed assessor rows (matches REST unreviewed reports):

```spl
| inputlookup stig_reviews
| search status=not_reviewed
```

One baseline’s rules:

```spl
| inputlookup stig_baseline_rules
| search baseline_id="<BASELINE_ID>"
```

Enrich with checklist/host via `lookup` on `stig_checklists` / custom fields as needed.

---

## 13. Persist handler implementation notes

File: `bin/stig_rest_handler.py`

1. **`sys.path.insert(0, bin_dir)`** at module load so `services` and `importers` resolve.
2. Class: `StigRestHandler(PersistentServerConnectionApplication)`; `handle(in_string)` → JSON parse → `_dispatch`.
3. Connect KV with **`session["authtoken"]`**.
4. Import body: read **`payload["payload"]`** as bytes for raw import; JSON endpoints use UTF-8 decode + `json.loads`.
5. Export endpoint returns **raw string** payload (not JSON-wrapped document).
6. Catch `PermissionError` → 403, `KeyError` → 404, `ValueError` → 400.

---

## 14. Audit logging

Logger name: `stigs_in_splunk.audit`.

Each mutation: INFO line `stig_audit {"action","entity_type","entity_id","user","details"}`.

Actions include: `create`, `update`, `delete`, `delete_blocked`, `import`, `import_deduplicated`.

Phase 2 may index `_internal` or dedicated index; PoC uses splunkd log only.

---

## 15. Testing requirements

### 15.1 Offline (no Splunk)

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Must include:

| Test | Validates |
|------|-----------|
| `test_xccdf_import` | Minimal XCCDF fixture → 1 rule, ids, hash |
| `test_baseline_fingerprint` | Stable hash; changes when version or check content changes |
| `test_cklb_export` | Export structure from fixture data |

### 15.2 Splunk integration (optional CI)

Env: `SPLUNK_PASSWORD` required; `SPLUNK_HOST`, `SPLUNK_PORT`, `SPLUNK_USERNAME`, `SPLUNK_APP` optional.

Script: `./scripts/run_splunk_tests.sh`

| Test module | Validates |
|-------------|-----------|
| `test_splunk_kvstore` | All six collection stanzas exist; direct KV insert/read |
| `test_splunk_integration` | REST: collection → import baseline → rules → host → checklist → reviews → PATCH review → CKLB export; **import same baseline twice** → same `_key` + `deduplicated` |

Use `tests/splunk_wait.py` to poll until KV collections exist after restart.

### 15.3 Demo script

`scripts/demo_rhel8_web01.py`:

1. Download/cache DISA `U_RHEL_8_V2R6_STIG.zip` from NIST NCP URL.
2. Extract `*-Manual-xccdf.xml`.
3. REST: create workspace → import baseline → create host `web-01` → create checklist → list reviews (expect **366** for RHEL 8).

---

## 16. Reference workflow (curl)

Replace IDs from responses.

```bash
BASE="https://localhost:8089/servicesNS/nobody/stigs_in_splunk"
AUTH="-k -u admin:password"

# 1 Workspace
curl $AUTH -X POST "$BASE/stig_collections" -H "Content-Type: application/json" \
  -d '{"name":"Lab","access_principals":["user:admin"]}'

# 2 Baseline
curl $AUTH -X POST "$BASE/stig_baselines/import?format=xccdf&source_uri=minimal_benchmark.xml" \
  --data-binary @tests/fixtures/minimal_benchmark.xml

# 3 Host
curl $AUTH -X POST "$BASE/stig_hosts" -H "Content-Type: application/json" \
  -d '{"stig_collection_id":"COLLECTION_ID","hostname":"web-01","ip_address":"10.0.0.10"}'

# 4 Checklist (spawns reviews)
curl $AUTH -X POST "$BASE/stig_checklists" -H "Content-Type: application/json" \
  -d '{"stig_collection_id":"COLLECTION_ID","host_id":"HOST_ID","baseline_id":"BASELINE_ID","title":"web-01 STIG"}'

# 5 Open finding
curl $AUTH -X PATCH "$BASE/stig_reviews/REVIEW_ID" -H "Content-Type: application/json" \
  -d '{"status":"open","finding_details":"Example finding","comments":"PoC"}'

# 6 Export CKLB
curl $AUTH "$BASE/stig_checklists/CHECKLIST_ID/export?format=cklb"
```

---

## 17. Known limitations (PoC)

| Limitation | Detail |
|------------|--------|
| Orphan data | Failed imports before KV `_key` fix may leave orphan `stig_baseline_rules` or empty baselines; no automatic GC. |
| No baseline dedup for legacy rows | Missing `content_fingerprint` until re-import. |
| Global baselines | All workspaces share baseline catalog. |
| Collection delete | Blocked when children exist unless `?cascade=true`; cascades workspace hosts/checklists/reviews/grants/assignment rows; baselines stay global. UCC Configuration delete only allows empty workspaces. |
| Export review join | By `group_id` only; empty `group_id` in XCCDF may weaken CKL/CKLB status linkage for some rules. |
| Batch rule insert | Sequential inserts via `batch_save`; large STIGs (~366 rules) take seconds. |
| Session capabilities shape | If Splunk sends `capabilities` as non-dict, admin checks may need hardening (Phase 2). |

---

## 18. Acceptance criteria (PoC done when)

1. App mounts and loads in Splunk 10 without symlink; six KV collections created.
2. Custom REST CRUD works for all documented endpoints; nested `import`, `export`, `rules` work.
3. RHEL 8 (or equivalent) XCCDF imports ~366 rules; duplicate import returns **200** + same `_key` + `deduplicated`.
4. Checklist create spawns one review per rule with `not_reviewed`.
5. Review PATCH persists `open` + finding text; export produces valid CKLB/CKL containing that status.
6. ACL: user not in `access_principals` cannot read workspace hosts/checklists/reviews.
7. `| inputlookup stig_reviews` returns rows in Search with app context.
8. Offline unit tests pass; integration tests pass when Splunk available.
9. App nav **Configuration** opens the UCC page. Workspaces can be created/edited/deleted there (KV `stig_collections`). Baselines can be imported from XCCDF/CKL/CKLB and deleted there. Editor & ingest settings save to `stigs_in_splunk_settings.conf` with **no HEC token field**.

---

## 19. Phase 2 backlog (preserve intent)

- Ingested findings → CIM / macros / dashboards.
- ~~Cross-revision review merge using `check_content_hash`~~ (see §11.4 `upgrade`).
- Workspace-scoped baselines or sharing model.
- Stronger audit (dedicated index, UI).
- KV cleanup jobs; cascade deletes; bulk review update.
