# STIG in Splunk — Build specification

This document is the **requirements and behavior spec** for the Splunk app **`stigs_in_splunk`**. It describes what the **shipped app does today** and records **proposed** additions that are not yet implemented. When this spec and the repo disagree, **the implementation wins** — update the spec to match (briefly note any intentional lag).

**Product goal:** Store DISA STIG **baseline** content and per-host **checklist review state** (assessor findings) in the Splunk **KV store**, exposed primarily through a **custom REST API** (clients must not depend on raw KV REST for grant-scoped business logic).

**Splunk version target:** Enterprise **10.x** (developed against 10.2.x). Python **3.9** inside the app persist handler.

---

## 1. Scope

### 1.1 Current implementation (shipped app)

| Area | Requirement |
|------|-------------|
| Persistence | Twelve KV collections in `default/collections.conf` with `enforceTypes = true` (core entities, grants, labels, review history, editor-settings fallback, ingest assignment rules/overrides — see §6.1). |
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

### 1.2 Not implemented (future / backlog)

- Custom SplunkUI **settings** page beyond UCC **Configuration** (editor uses `/stig_settings` adapter only for selected fields).
- Search macros, CIM Vulnerability datamodel, eventtypes for ingested STIG events.
- Automatic XCCDF **results** `pass`/`fail` → assessor status mapping on import (Evaluate-STIG results import applies Watcher-shaped review fields instead).
- **RMF packages** (authorization boundary labels) — proposed in §20; not in KV or REST today.
- See also §19 for other deferred items.

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
globalConfig.json          # UCC meta + pages.configuration (workspaces, baselines, settings)
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

**App identity:** `package.id = stigs_in_splunk`, label “STIG in Splunk”, version from `globalConfig.json` / `--ta-version` (default `0.1.0`).

### 4.1 UCC packaging pattern

- **`globalConfig.json`** defines `meta` and **`pages.configuration`** (no `pages.inputs`). This is a REST + KV app with a UCC Configuration UI, not a modular-input TA.
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
| `ui_theme_preset` | string | `tokyo_night` | UCC or **`stig_write`** | Editor palette: `tokyo_night`, `catppuccin`, `rose_pine`, `light`, `follow_splunk`, or `custom`. Legacy installs with only `ui_color_scheme` map `light` / `follow_splunk` / `dark` → `light` / `follow_splunk` / `tokyo_night` on read. |
| `ui_theme_custom` | string (JSON) | `""` | UCC or **`stig_write`** | Optional theme overrides. With preset **custom**, full palette JSON; otherwise merges `colors` / `cssVars` onto the preset (see `ui/src/themes/customTheme.js`). |
| `ui_color_scheme` | string | `dark` | *(legacy)* | Deprecated; still returned when present in conf. Prefer `ui_theme_preset`. Values: `dark`, `light`, `follow_splunk`. |

**Intentionally excluded (never stored in app settings):**

| Field | Where it lives |
|-------|----------------|
| `hec_token` | Splunk HTTP Event Collector input stanza **`[http://stig_findings]`** in `inputs.conf` (read server-side by `services/hec.py::lookup_hec_token`). Never returned from `/stig_settings`, never written from REST bodies (stripped in `save_settings`). |

**UCC admin REST (Configuration UI backend):** `GET|POST /servicesNS/nobody/stigs_in_splunk/stigs_in_splunk_settings/general` (Splunk Web proxies `stigs_in_splunk_settings` per `web.conf`). Field definitions and help text are authored in **`globalConfig.json`** tab `general`.

**Workspace names** are unique (case-insensitive). The UCC table row id is the workspace `name`. Baseline table row id is `ucc_name` (set on import; falls back to `_key` for legacy rows).

Do not upload a DISA library zip through the UCC file widget. Splunk wraps that file in EAI XML **before** the Python handler runs, so a 360MB–1GB zip fails with `Unable to xml-parse` (row id such as `July_2026`). Configuration Baselines is list/delete only. The Import page chunk-uploads the zip to persist `/stig_baselines/jobs` (4MB JSON chunks, staged under `$SPLUNK_HOME/var/run/stigs_in_splunk/baseline_jobs/`, max 2GB) and **imports every Manual-xccdf automatically**. Large collection archive exports may use `POST /stig_collections/{id}/jobs` (artifacts under `collection_jobs/`, same **6h TTL**). Never send the zip through an EAI/`admin_external` handler.

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
| `stig_review_accept` | Accept/reject submitted reviews when also allowed by workspace grant / `review_accept_principals` (see §8.1) |

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
- **`role_admin`:** enable all STIG capabilities for admin UX

Map capabilities to HTTP methods in **each** `restmap.conf` stanza (see §7).

### 5.3 REST base URL

```text
https://<host>:8089/servicesNS/nobody/stigs_in_splunk
```

Resources: `stig_collections`, `stig_collection_grants` (nested under collections), `stig_hosts`, `stig_baselines`, `stig_checklists`, `stig_reviews`, `stig_findings`, `stig_imports`, `stig_settings` (§4.3.1, §11.7), `stig_assignment_rules`, `stig_host_baseline_assignments`, `stig_assignment/preview`, `stig_readiness` (§11.8).

Authentication: Splunk session or Basic Auth (`-u user:pass`). TLS verify often disabled in dev (`curl -k`).

---

## 6. Splunk configuration (detailed)

### 6.1 `default/collections.conf`

Twelve stanzas (all `enforceTypes = true`):

| Stanza | Role |
|--------|------|
| `stig_collections` | Workspaces |
| `stig_collection_grants` | Workspace grant roles + optional ACL |
| `stig_labels` | Workspace asset labels |
| `stig_hosts` | Assessed assets |
| `stig_baselines` | STIG revision catalog headers |
| `stig_baseline_rules` | Rules per baseline |
| `stig_checklists` | Host × baseline bindings |
| `stig_reviews` | Per-rule assessor state |
| `stig_review_history` | Append-only review change log (§7.7) |
| `stig_editor_settings` | Legacy settings KV fallback (§7.10) |
| `stig_assignment_rules` | Ingest workspace resolver rules (§7.8) |
| `stig_host_baseline_assignments` | Host×STIG ingest overrides (§7.9) |

**Accelerated fields (for KV queries):**

| Collection | Accelerated index |
|------------|-------------------|
| `stig_collection_grants` | `{"stig_collection_id": 1}` |
| `stig_labels` | `{"stig_collection_id": 1}` |
| `stig_hosts` | `{"stig_collection_id": 1}` |
| `stig_baselines` | `{"content_fingerprint": 1}`, `{"stig_collection_id": 1}` |
| `stig_baseline_rules` | `{"baseline_id": 1, "group_id": 1}` |
| `stig_checklists` | `{"stig_collection_id": 1}` |
| `stig_reviews` | `{"checklist_id": 1, "status": 1}` |
| `stig_review_history` | `{"stig_collection_id": 1, "created_at": -1}`, `{"review_id": 1, "created_at": -1}` |
| `stig_assignment_rules` | `{"priority": 1, "enabled": 1}` |
| `stig_host_baseline_assignments` | `{"hostname": 1, "benchmark_id": 1}` |

**`default/app.conf`:** include `[triggers] reload.collections = simple`.

### 6.2 `default/restmap.conf`

**Critical Splunk constraint:** only **one** `match =` per stanza; duplicate `match` keys in one stanza **overwrite** — only the last survives.

Implement **one stanza per top-level persist path** (duplicate `match` keys in one stanza overwrite — only the last survives). Shipped paths include:

- `/stig_collections`, `/stig_findings`, `/stig_hosts`, `/stig_baselines`, `/stig_checklists`, `/stig_reviews`
- `/stig_imports`, `/stig_settings`, `/stig_readiness`
- `/stig_assignment_rules`, `/stig_host_baseline_assignments`, `/stig_assignment/preview`
- `/stigs_in_splunk_baseline` — UCC Configuration baseline list/delete adapter (no zip upload on EAI)

UCC **admin_external** handlers for Configuration workspaces/settings are merged at build time (see §4.1).

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
fields_list = _key, stig_id, title, version, benchmark_status, rule_count, content_fingerprint, source_uri, imported_at
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
| `review_accept_principals` | string | JSON array of `user:` / `role:` principals allowed to accept/reject submitted reviews in this workspace (in addition to grant owner/manager and `stig_admin`). |
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
| `hostname`, `description`, `ip_address`, `fqdn`, `mac_address` | string | CKL/CKLB target; `description` optional (255 chars) |
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
| `benchmark_status` | string | XCCDF Benchmark status (`accepted`, `draft`, `interim`, …). Unpinned “latest” catalog resolution skips `draft` / `interim`. |
| `xccdf_benchmark_id` | string | XCCDF Benchmark `@id` |
| `rule_count` | number | Count at import |
| `source_type` | string | `xccdf` \| `cklb` \| `ckl` |
| `source_uri` | string | Filename/URL hint from client |
| `ucc_name` | string | Unique id for the UCC Configuration table row |
| `content_fingerprint` | string | SHA-256 hex; dedup key (§9) |
| `imported_at` | time | |
| `imported_by` | string | |
| `stig_collection_id` | string | Optional workspace owner; **empty = global** (legacy rows). Workspace-scoped baselines are visible only to users with **read** on that `stig_collection`. |

**Catalog scope:** Global baselines remain shared. Workspace-scoped rows are private to the owning workspace (plus **stig_admin**). `GET /stig_baselines` returns globals plus baselines for workspaces the caller can read. Query `stig_collection_id` narrows to globals + that workspace (requires workspace read). Import without scope creates globals; `stig_collection_id` on `POST /stig_baselines/import` (query or JSON) requires workspace **write**. Dedup (`content_fingerprint`, optional `stig_id`+`version`) is per scope. Existing checklist `baseline_id` references are unchanged.

**Default / assign resolution** (when `baseline_id` omitted): explicit id → workspace `default_baseline_map` (pinned revision per STIG; unchanged by this rule) → latest matching revision in **workspace-scoped** catalog → latest **global** catalog match. Unpinned “latest” picks the highest DISA-style `VxRy` version/release among catalog rows for that `stig_id` (tie-break: newest `imported_at`), and **excludes** benchmark revisions whose `benchmark_status` is `draft` or `interim`. An explicit `version` query/body field may still resolve a draft row. Aligns with STIG Manager [user guide §2.9.3.2](https://stig-manager.readthedocs.io/en/latest/user-guide/user-guide.html); implementation: `find_baseline_by_stig` in `services/baselines.py` and `resolve_baseline_id` in `services/baseline_defaults.py`.

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
| `valid` | bool | Server-computed against workspace `review_requirements` (exposed on GET/findings; updated on PATCH/submit). |
| `package_id` | string | Optional **Evaluate-STIG / CKLB package id** on the review (ingest, PATCH, export). **Not** the proposed RMF package entity (§20). |
| `ingest_lock` | bool | When **true**, HEC/reconcile must **not** overwrite this review. Default false; incoming is authoritative. |
| `workflow_state` | string | `draft` \| `submitted` \| `accepted` (reject returns to `draft`; see FEATURE_PARITY.md) |
| `submitted_at`, `submitted_by` | time / string | Set on submit |
| `accepted_at`, `accepted_by` | time / string | Set on accept |
| `rejected_at`, `rejected_by`, `reject_feedback` | | Set on reject (feedback optional) |
| `updated_at` | time | |
| `updated_by` | string | Set on every update |

### 7.7 `stig_review_history`

Append-only audit of **assessor-visible** review changes (not a full document snapshot). Rows are inserted when REST PATCH/submit/accept/reject/batch, checklist ingest apply, or baseline upgrade mutates tracked fields on a review.

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | KV id |
| `review_id` | string | FK → `stig_reviews._key` |
| `stig_collection_id`, `checklist_id`, `host_id`, `baseline_id` | string | Denormalized for workspace list filters and grant ACL |
| `group_id`, `rule_id`, `rule_version` | string | Rule identity at change time |
| `action` | string | `update` \| `submit` \| `accept` \| `reject` \| `ingest` \| `upgrade` |
| `previous_status`, `new_status` | string | Assessor status |
| `previous_workflow_state`, `new_workflow_state` | string | Governance state |
| `changed_fields` | string | JSON array of changed field names (`status`, `finding_details`, `comments`, `ingest_lock`, `workflow_state`, `package_id`, `reject_feedback`) |
| `summary` | string | Short human-readable line (bounded length; no full finding text) |
| `actor` | string | Splunk username |
| `created_at` | time | Event time |

**Ingest:** `apply_review_seeds` records `action=ingest` when an incoming checklist/HEC apply changes a review. Rows are **not** written when ingest skips a review (`ingest_lock` or non-draft workflow). History writes are synchronous KV inserts (cheap); large zip imports may produce many rows.

**Governance:** `submit` / `accept` / `reject` always append a history row when the REST action succeeds, even if assessor field values are unchanged; `reject_feedback` is included in `changed_fields` when it changes.

**Workspace list:** `GET /stig_collections/{id}/review-history` loads all KV rows for the workspace then filters and paginates in the handler (acceptable for P2; very large histories may be slow—use per-review history or query filters).

**Retention:** Per-workspace `review_history_config` JSON on `stig_collections`: `enabled` (default true) and `max_records_per_review` (default **15**, max **15** per STIG Manager). When disabled, new rows are not written and history GET endpoints return no rows. When enabled, each insert trims oldest rows for that `review_id` beyond the cap; list endpoints also apply the cap before pagination. Reducing the cap does not delete existing KV rows until the next review update. REST `GET/PATCH /stig_collections/{id}/review_history_config`. Cascade workspace delete removes all history rows for that `stig_collection_id`.

### 7.8 `stig_assignment_rules`

Global (not workspace-scoped) ordered rules that resolve **which workspace** receives HEC/checklist ingest when `trust_event_collection_id` is false. Evaluated by ascending `priority` (then `_key`); first enabled match wins when `stop_on_match` is true.

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | Rule id |
| `priority` | number | Lower sorts earlier (default 100 on create) |
| `enabled` | bool | Default true |
| `name` | string | Display label |
| `target_stig_collection_id` | string | FK → workspace (required) |
| `match_json` | string | JSON object; all specified predicates must match (AND). Supported keys: `hostname` + optional `hostname_mode` (`glob`, `regex`, `exact`, `suffix`), `benchmark_id`, `package_id` (Evaluate-STIG/CKLB id on the **event**, not RMF), `source_product`, `collection_name` / `collectionName`, `ip_cidr`. Empty/absent predicate ⇒ match any. |
| `stop_on_match` | bool | Default true |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

REST: `GET/POST /stig_assignment_rules`, `GET/PATCH/DELETE /stig_assignment_rules/{id}`. **DELETE** requires **`stig_admin`**. Create/update require **`stig_write`**. List/get require **`stig_read`**.

### 7.9 `stig_host_baseline_assignments`

Hostname × logical `benchmark_id` (`stig_id`) overrides that force a target workspace before assignment rules. Optional `expires_at` (epoch seconds; 0 = never).

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | Override id |
| `hostname` | string | Normalized casefold key |
| `benchmark_id` | string | STIG id on the event (`stig.stig_id` / `benchmarkId`) |
| `target_stig_collection_id` | string | FK → workspace |
| `note` | string | Optional |
| `expires_at` | number | Optional expiry |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

REST: `GET/POST /stig_host_baseline_assignments`, `GET/PATCH/DELETE /stig_host_baseline_assignments/{id}` (same capability pattern as §7.8).

**Preview:** `GET|POST /stig_assignment/preview` with JSON `{event: {...}}` (or query `event` JSON) returns resolved `stig_collection_id` and reason (`override`, `rule`, `event_collection_id`, `default`, `forced_import`). Requires **`stig_read`**.

### 7.10 `stig_editor_settings`

Legacy KV fallback for editor/ingest settings when `stigs_in_splunk_settings.conf` `[general]` is absent (see §4.3.1). Fields mirror public `/stig_settings` keys (no `hec_token`).

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
| `stig_host`, `stig_checklist`, `stig_review` | Via parent `stig_collection_id` (+ grant ACL dimensions) |
| `stig_baseline`, `stig_baseline_rule` | **Global** rows (empty `stig_collection_id`) visible per catalog rules in §7.3; **workspace-scoped** baselines require read on that workspace |
| `stig_assignment_rules`, `stig_host_baseline_assignments` | Global tables; REST list/mutate per §7.8–7.9 capabilities (not grant-filtered) |

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

`GET /stig_checklists/{id}/export?format=cklb|ckl|xccdf`

- Join checklist + host + baseline metadata + baseline rules + reviews.
- Match reviews to rules primarily by `group_id` (see §17 export limitation).
- **CKLB / CKL:** STIG Viewer–compatible checklist files (JSON or XML).
- **XCCDF (`format=xccdf`):** OpenSCAP / Evaluate-STIG–shaped **results** XML (`TestResult` + `rule-result` per rule). Not a full SCAP source data stream or Manual STIG benchmark bundle. Baseline rules with no resolvable XCCDF rule `idref` are **omitted** (CKL/CKLB still emit those rule rows).
- Response: JSON string (CKLB) or XML string (CKL or XCCDF); appropriate `Content-Type`.

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
| GET | `/stig_collections/meta/metrics` | Query `offset?`, `limit?` (max 500) | Cross-workspace metrics: `summary` rolled up across **all** readable workspaces; `workspaces[]` paginated only. Uses the same grant filter as `GET /stig_collections`. Requires **stig_read**. **Performance:** one `collection_metrics` KV pass per readable workspace for `summary` (and the same passes populate paginated rows); large orgs should use a modest `limit` for the table or call `/summary` when only rollups are needed. |
| GET | `/stig_collections/meta/metrics/summary` | — | Same org-wide `summary` as meta metrics; no pagination; omits `workspaces[]`. |
| POST | `/stig_collections` | JSON `{name, description?, access_principals?, is_default?}` | **201** created record |
| GET | `/stig_collections/{id}` | — | Record or **404** |
| PATCH/PUT | `/stig_collections/{id}` | Partial JSON | Updated record. Setting `is_default` true unsets the previous default. |
| DELETE | `/stig_collections/{id}` | Query `cascade=true` or JSON `{"cascade": true}` when the workspace has dependent rows | `{deleted, cascade, removed}`; requires **stig_admin**. Cannot delete the default workspace. Without `cascade`, **409** when hosts, checklists, reviews, grants, or assignment rows remain (audit `delete_blocked`). Response `children` is **per-type** counts (reviews may overlap checklists; do not sum all keys for a deduplicated total). With `cascade=true`, removes workspace-scoped hosts, checklists, reviews, grants, and assignment rules/overrides; **global baselines are untouched**. Empty workspaces delete without `cascade`. |
| GET | `/stig_collections/{id}/metrics` | — | Workspace metrics: `totals`, `completion`, `by_status`, `by_severity`, `open_by_severity`, `review_ages` / `minTs` / `maxTs` (evaluation content), `maxTouch` (last workflow status change). Requires **stig_read** and workspace access (**404** if hidden). |
| GET | `/stig_collections/{id}/metrics/export` | Query `grouping?`, `style?`, `format?`, `rmf_package_id?` | Grouped metrics export (STIG Manager §2.4.1.2): `grouping` = `collection` \| `asset` \| `stig` \| `label` \| `ungrouped`; `style` = `summary` \| `detail` (detail adds automated `*ResultEngine` splits); `format` = `json` \| `csv`. JSON includes `rows[]` with SM field names (`assessments`, `minTs`, `maxTs`, `maxTouch`, result/workflow counts). **404** if hidden; **400** on invalid params. |
| GET | `/stig_collections/{id}/findings` | Query filters (see §11.6) | Paginated findings report for assessors. Default filter: `status=open`. |
| GET | `/stig_collections/{id}/findings/aggregate` | `group_by?`, filters (see §11.6) | Governance-open counts by group, rule, and/or CCI. |
| GET | `/stig_collections/{id}/unreviewed/assets` | Filters (see §11.6) | Per-host unreviewed counts (`status=not_reviewed`). |
| GET | `/stig_collections/{id}/unreviewed/rules` | Filters (see §11.6) | Per-rule unreviewed counts with hostnames. |
| GET | `/stig_collections/{id}/poam` | `format?` (`json`, `csv`, `xlsx`) | POA&M-style export for governance-open findings. |
| POST/PUT | `/stig_collections/{id}/archive/ckl` | Query or JSON `host_id?`, `baseline_id?` | Zip archive of all CKL checklists in the workspace (grant ACL applied). **400** when no checklists match. **404** when workspace hidden. Response JSON: `{filename, format, count, files, content_base64, stig_collection_id, filters}`. Zip entry names: `{hostname}_{stig_id}_{version}.ckl`. |
| POST/PUT | `/stig_collections/{id}/archive/cklb` | Same filters as CKL archive | Same as CKL archive with `.cklb` entries. |
| POST/PUT | `/stig_collections/{id}/archive/xccdf` | Same filters as CKL archive | Zip of XCCDF **results** (`TestResult` + `rule-result` per checklist) derived from KV reviews. Not a full SCAP source data stream or Manual STIG benchmark bundle. Zip entry names: `{hostname}_{stig_id}_{version}-results.xml`. Response `format`: `xccdf`. Per-checklist: `GET /stig_checklists/{id}/export?format=xccdf`. |
| POST | `/stig_collections/{id}/jobs` | JSON `{operation: "archive_export", format, host_id?, baseline_id?}` | **201** async archive export job (`job_id`, `status`: `pending` → `running` → `succeeded` \| `failed`). Same export ACL as sync archive (workspace read; **404** when hidden). Creator-only `GET`/`DELETE` on the job (like baseline zip jobs). Worker reconnects KV with the request `authtoken` (does not share the parent persist `service` across threads). Staged zip under `$SPLUNK_HOME/var/run/stigs_in_splunk/collection_jobs/{job_id}/` (**6h TTL**, lazy delete on read after expiry — no global sweeper; abandoned jobs linger until TTL + poll). Poll `GET .../jobs/{jobId}`; download `GET .../jobs/{jobId}/download` returns the same JSON shape as sync archive (`content_base64` in JSON — same practical size limits as `POST .../archive/*`; no separate cap beyond disk and Splunk REST payload limits). Collection zip **import** remains synchronous on `POST .../imports`. |
| GET | `/stig_collections/{id}/jobs/{jobId}` | — | Job status and `result.download_path` when succeeded. |
| GET | `/stig_collections/{id}/jobs/{jobId}/download` | — | Zip payload JSON (`content_base64`, `filename`, `count`, `files`) when job succeeded; **400** otherwise. |
| DELETE | `/stig_collections/{id}/jobs/{jobId}` | — | Remove staged job directory (creator only). |
| POST/PUT | `/stig_collections/{src}/export-to/{dst}` | JSON `{host_ids: [string]}` | Bulk transfer hosts from `src` to `dst` workspace. Checklists follow each host (host row updated before checklists; single-host rollback on checklist failure). Rejects move when destination already has same hostname (case-insensitive), per-host `error`: `destination_hostname_collision`. **403** without write on either workspace (checked before the loop); **404** when workspace missing/hidden; **400** when `host_ids` empty or `src` equals `dst`. Per-host `results` (`moved`, `skipped`, `error`); `summary` counts. Hosts are processed in order with **no request-level rollback**—successful moves stay committed if later ids fail. **201** when `summary.moved > 0` (even if some hosts failed/skipped), else **200**. Audit: `transfer` on `stig_host` per successful move. |
| POST/PUT | `/stig_collections/{id}/clone` | JSON `{name?, description?, access_principals?, async?, pin_all_stigs_to_defaults?, copy_hosts?, copy_checklists?, copy_reviews?, copy_grants?, copy_labels?, copy_metadata?, copy_baseline_defaults?, copy_review_requirements?, options?}` | Clone workspace to a new `stig_collection`. Requires workspace **read** on source and **`stig_write`** (or admin) to create destination. **201** with `{stig_collection_id, stig_collection, source_stig_collection_id, options, summary, id_map}`; optional `options_coerced` when dependent flags were adjusted. **`async: true`** → **202** with pollable collection job (`GET .../jobs/{jobId}`) instead of synchronous **201**. **`pin_all_stigs_to_defaults`** (alias `options.pinAllStigsToDefaults`) sets each cloned checklist `baseline_id` from the source default map (`summary.pinned_checklists`); when false, checklists keep copied `baseline_id` values. **400** for contradictory explicit flags (e.g. `copy_reviews` true with `copy_hosts` false, `pin_all_stigs_to_defaults` without checklists, or `copy_grants` without `copy_hosts`/`copy_labels` when source grants use `acl_host_ids`/`acl_labels`). Grant ACL ids are remapped 1:1; empty remaps never widen restricted scope. **Global baselines are not copied** (checklists keep `baseline_id` references). On failure after destination create, rolls back with cascade delete; audit `clone_rollback_failed` if rollback fails. Audit: `clone` on destination workspace; `create` on each cloned host. **Defaults** when flags omitted: `copy_hosts`, `copy_checklists`, `copy_reviews`, `copy_labels`, `copy_metadata`, `copy_baseline_defaults`, `copy_review_requirements` = **true**; `copy_grants`, `pin_all_stigs_to_defaults`, `async` = **false**. Implicit coupling: `copy_hosts` false forces checklists/reviews off; `pin_all_stigs_to_defaults` forces `copy_baseline_defaults` true (listed in `options_coerced`). Optional `name` defaults to `{source name} (clone)` with numeric suffix if taken. STIG Manager aliases: `options.grants`, `options.stigMappings` (`withReviews` / `withoutReviews`). Async clone also via `POST .../jobs` `{operation: "clone", ...}`. |

Default `access_principals` on create: `["user:<creator>"]` if omitted. The Default holding workspace uses `[]` (any user with STIG caps).

`POST /stig_imports` may omit `stig_collection_id`; the Default workspace is used. Move a host with `PATCH /stig_hosts/{id}` `{stig_collection_id}` (checklists follow the host; reviews stay keyed by `checklist_id`). Bulk move: `POST /stig_collections/{src}/export-to/{dst}` with JSON `{host_ids: [...]}` — requires workspace **write** on source and destination; returns per-host `results` and `summary`; emits audit `transfer` per moved host. On move, `label_ids` are kept only when the label exists in the destination workspace; grants are not copied.

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
| GET/PATCH | `/stig_hosts/{id}/metadata` | Optional asset metadata (`metadata` JSON on host). **GET** returns `{stig_host_id, metadata}` (empty object when unset). Respects workspace read and restricted grant `acl_host_ids` / `acl_labels` (same as host GET — out-of-scope host → **404**). **PATCH** requires workspace **write**; body `{metadata: {...}}` shallow-merges keys (set a key to JSON `null` to remove). `{replace: true, metadata: {...}}` replaces the entire object. `{clear: true}` removes all keys. Top-level `"metadata": null` returns **400** (use `clear: true` to wipe). Values must be JSON-serializable; non-object `metadata` returns **400**. Audit event `stig_host_metadata` on successful PATCH. |
| PATCH/DELETE | `/stig_hosts/{id}` | — | PATCH fields optional; DELETE requires **stig_admin** |
| GET | `/stig_collections/{id}/assets/csv` | `host_ids?` (comma-separated) | STIG Manager–style CSV export (`Name`, `Description`, `IP`, `FQDN`, `MAC`, `Non-Computing`, `STIGs`, `Labels`, `Metadata`). **200** `text/csv` with `Content-Disposition` and `X-Stig-Row-Count`. |
| POST | `/stig_collections/{id}/assets/csv` | — | JSON `{csv, submit?}`. `submit=false` (default) validates rows; `submit=true` creates/updates hosts, assigns STIGs, creates missing labels. **200** report; **201** when `submit=true` and at least one host created. |

DELETE requires **stig_admin**. Writes require workspace **stig_write** access.

### 11.3 `stig_baselines`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_baselines` | List baseline headers visible to the caller (globals + readable workspace catalogs). Query `stig_collection_id?` → globals + that workspace only. |
| GET | `/stig_baselines/hierarchy` | Benchmark-centric library (same visibility + optional `stig_collection_id` filter). Revisions include `stig_collection_id` / `scope`. |
| GET | `/stig_baselines/compare` | Read-only revision diff. Query `from_baseline_id` + `to_baseline_id` (same `stig_id`). Returns summary counts plus `added`, `removed`, and `changed` rule rows; `changed` entries list `changed_fields` and per-field `from`/`to` text (library browse only). **404** when either baseline is not visible. |
| GET | `/stig_baselines/by_stig/{stigId}` | One benchmark entry from hierarchy (404 when unknown) |
| GET | `/stig_baselines/rule/{ruleKey}` | Stable rule detail by KV `_key` on `stig_baseline_rules` (includes parent baseline summary) |
| GET | `/stig_baselines/{id}/rules/{ruleRef}` | Rule in baseline context. `ruleRef` may be the rule KV `_key`, composite `group_id\|rule_id` (V-id\|SV-id), or SV-id via `rule_id` / `rule_id_src`. A bare V-id is not accepted (avoids first-row scans). Optional query `group_id` disambiguates duplicate SV-ids in one baseline. Ambiguous matches return **404**. |
| POST | `/stig_baselines/import` | Query `format` (`xccdf` \| `cklb` \| `ckl` \| `zip`), `source_uri`, optional `stig_collection_id`; JSON body may also set `stig_collection_id`. Workspace scope requires workspace **write**. Zip walks nested archives and imports only `*Manual-xccdf.xml` STIG baselines. |
| GET | `/stig_baselines/rules/{ruleRef}` | Rules matching `ruleRef` across **visible** baselines (`rule_id`, `rule_id_src`, `rule_version`, or `group_id`; DISA `xccdf_mil.disa.stig_rule_` prefix stripped). Query `stig_id?` optional. **404** when no matches. |
| GET | `/stig_baselines/ccis/{cci}` | Rules whose imported `ccis` JSON array contains the CCI (normalized to `CCI-…`), on visible baselines. Query `stig_id?` optional. **200** with empty `matches` when none. |
| GET | `/stig_baselines/groups/{groupId}` | Rules with `group_id` (V-id) on visible baselines. Query `stig_id?` optional. |
| GET | `/stig_baselines/{id}/rules` | All rules for baseline |
| GET/POST | `/stig_baselines/gc_orphan_rules` | Admin orphan rule GC. **GET** and default **POST** are dry-run reports (`orphan_count`, `orphans[]`, `skipped_no_key_count`). Destructive delete when **POST** with `dry_run=false` or `confirm=true` (query or JSON). Removes only deletable `stig_baseline_rules` rows (requires KV `_key`); orphans without `_key` are listed but skipped. Does **not** cascade to checklists or reviews. Audits only when `deleted_count > 0`. Requires **stig_admin** in handler (`restmap` admits GET/POST with read/write capabilities). |

**Reserved path literals:** The first segment after `/stig_baselines/` cannot be used as a baseline KV `_key` for `GET /stig_baselines/{id}` when it equals `import`, `jobs`, `gc_orphan_rules`, `hierarchy`, `compare`, `by_stig`, `rules`, `ccis`, `groups`, or `rule` (those paths are routed to catalog/import handlers). UCC `ucc_name` values should avoid these tokens.
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
| GET | `/stig_checklists/{id}/export` | Query `format=cklb|ckl|xccdf` — CKLB/CKL checklist files or XCCDF **results** XML (see §10.2; not a SCAP bundle). |
| POST/PUT | `/stig_checklists/export_bulk` | JSON `{checklist_ids?, stig_collection_id?, format, host_id?, baseline_id?}` | Zip of multiple checklists (`format`: `ckl`, `cklb`, or `xccdf`). Either `checklist_ids` **or** `stig_collection_id` (workspace-scoped, optional host/baseline filters). Workspace-scoped calls use the same read ACL as archive export: missing or unreadable workspace → **404** (not **403**). **400** when filters match no checklists. Same zip/filename rules as collection archive. |
| POST/PUT | `/stig_checklists/{id}/upgrade` | `{baseline_id}` — same `stig_id`, newer revision; merge reviews when `check_content_hash` matches |
| POST | `/stig_imports` | Query `format=ckl\|cklb\|zip\|xccdf-results-zip\|xccdf-results`, `source_uri`, `stig_collection_id`; raw body (see §11.4.1) |
| POST | `/stig_collections/{id}/imports` | JSON `{files: [{source_uri, format?, content\|content_base64}]}` **or** raw zip body (`format=zip` query or PK magic). Batch CKL/CKLB/XCCDF-results collection import; workspace **write** required. |
| GET/POST/DELETE | `/stig_collections/{id}/baseline_defaults` | Workspace default `baseline_id` per `stig_id` (`default_baseline_map` on collection) |
| GET/PATCH | `/stig_collections/{id}/review_requirements` | Workspace review validation policy (`review_requirements` JSON on collection). **GET** returns `{stig_collection_id, review_requirements, defaults}`. **PATCH** body `{review_requirements: {...}}` or flat policy fields; requires workspace **write**. |
| GET/PATCH | `/stig_collections/{id}/review_aging` | Workspace review aging policy (`review_aging_config` JSON on collection). Alias path segment `review-aging` accepted. **GET** returns `{stig_collection_id, review_aging, defaults, stale_threshold_seconds}`. **PATCH** body `{review_aging: {...}}` or flat policy fields; requires workspace **write** (manager/owner grant or `stig_write`). Default: `enabled=false`, `stale_after_days=90`, optional `stale_after_hours` override, filters `statuses`, `workflow_states`, `severities` (empty severities = all). Staleness uses review KV `updated_at` (last material change); does **not** auto-reset status. |
| GET | `/stig_collections/{id}/review_aging/stale` | Lists reviews older than the workspace threshold matching filters; same grant ACL as metrics/findings. Query `limit` (default 500, max 2000). When aging disabled, returns `stale_count=0` and empty `items`. Each item includes `aging_stale`, `aging_last_change_at`, `aging_age_seconds`, `aging_threshold_seconds` (report flags only; KV rows are not mutated). |
| GET/POST | `/stig_collections/{id}/review_aging/apply` | Preview or execute **action rules** in `review_aging.rules` (ordinal, per-rule enable, trigger `ts`/`status_ts`/`touch_ts`, interval, actions delete/set Saved/Submitted/Not Checked/Informational, targets collection/asset/STIG/label). **GET** and default **POST** are dry-run (`planned`, `matched_count`). Execute when **POST** with `dry_run=false` or `confirm=true`. Requires workspace **write**. Audits mutations; delete removes review + history rows. |
| GET/PATCH | `/stig_settings/review_aging_job` | App Manager **Update Aged Reviews** toggle (`stig_admin`). When enabled, saved search **STIG review aging apply** (`\| stigkvreviewagingapply`) may POST `/stig_imports/review_aging_apply` with execute. |
| GET/POST | `/stig_imports/review_aging_report` | Scheduled-search helper: stale reviews for **grant-visible** workspaces with `review_aging.enabled=true` (same ACL as `GET /stig_collections`). Query `limit` (default 2000, max 2000) caps `items`; `stale_count` is the full total and `truncated` is true when capped. Invoked by `\| stigkvreviewaging` (runner `sessionKey`) and saved search **STIG review aging report** (disabled by default). |
| GET/POST | `/stig_imports/review_aging_apply` | Runs enabled rules for all workspaces when the app job is enabled. Default dry-run; execute via `dry_run=false`/`confirm=true` (scheduled search uses execute). Scans all workspaces (not grant-filtered). |
| GET/PATCH | `/stig_collections/{id}/metadata` | Optional workspace metadata (`metadata` JSON on collection). **GET** returns `{stig_collection_id, metadata}` (empty object when unset). **PATCH** requires workspace **write**; body `{metadata: {...}}` shallow-merges keys (set a key to JSON `null` to remove). `{replace: true, metadata: {...}}` replaces the entire object. `{clear: true}` removes all keys. Top-level `"metadata": null` returns **400** (use `clear: true` to wipe). Values must be JSON-serializable; non-object `metadata` returns **400**. |
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
| PATCH/PUT | `/stig_reviews/{id}` | `{status?, finding_details?, comments?, package_id?, ingest_lock?}` (`package_id` = Evaluate-STIG/CKLB id, not RMF — §7.6) |
| POST | `/stig_reviews/{id}/submit` | Assessor submit (`stig_write` + workspace grant); review must be valid |
| POST | `/stig_reviews/{id}/accept` | Owner/manager accept (`stig_review_accept`, grant role, or `review_accept_principals`) |
| POST | `/stig_reviews/{id}/reject` | `{reject_feedback?}` — returns review to `draft` |
| POST | `/stig_reviews/batch` | Field batch: `{reviews: [{_key, ...}]}` **or** governance: `{action, review_ids[], reject_feedback?}` (mutually exclusive; max 500 ids). Both return `{updated: [...], errors: [...], summary: {total, succeeded, failed}}`; governance adds `action`. |
| GET | `/stig_reviews/{id}/history` | `{review_id, history: [...], pagination}` — newest first; query `limit?` (default **100**, max **500**), `offset?`, `since?` / `until?` (epoch). Same read ACL as `GET /stig_reviews/{id}`. |
| GET | `/stig_reviews/{id}/peers` | `{review_id, rule_id, group_id, rule_version, stig_collection_id, peers: [...]}` — other hosts in the workspace with the same rule on a checklist the caller can read (same `baseline_id` or same catalog `stig_id` across revisions). Each peer includes `review_id`, `host_id`, `hostname`, `status`, `workflow_state`, assessor text + snippets, `updated_at`. |
| POST | `/stig_reviews/{id}/copy_from/{peerReviewId}` | Copies assessor fields from a visible peer into the anchor review. Body optional `{fields?: ["status","finding_details","comments"]}` (default all three). Requires `stig_write`; anchor must be editable draft. Peer must appear in `GET .../peers` for the same anchor. Returns `{review, copied_from, copied_fields}`. Enforces `review_requirements` like PATCH. **403** when not editable; **404** when anchor or peer not visible. |
| GET | `/stig_collections/{id}/review-history` | Workspace-scoped timeline; query `host_id?`, `baseline_id?`, `rule_id?`, `review_id?`, time range, pagination. Restricted grants filter by host/baseline/label scope. |

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

SplunkUI **Collection dashboard** (`stig_collection_dashboard_ui`) loads metrics, findings, **aggregated open findings** (by group, rule, CCI), **unreviewed** rules/assets reports, and **POA&M** CSV/XLSX export for governance-open rows. SplunkUI **All workspaces** (`stig_meta_collection_dashboard_ui`) loads `GET /stig_collections/meta/metrics` for grant-filtered cross-workspace rollups. Optional Simple XML dashboard: `stig_collection_metrics_lookup`.

### 11.7 `stig_settings` (app configuration adapter)

JSON adapter over **`stigs_in_splunk_settings.conf`** `[general]` (see §4.3.1). STIG Manager migrators can treat this as the Splunk-shaped **`/op/configuration`** surface for editor + ingest (not workspace catalog).

| Method | Path | Capability | Body | Response |
|--------|------|------------|------|----------|
| GET | `/stig_settings` | **`stig_read`** | — | Public settings object (no `hec_token`). |
| POST / PATCH / PUT | `/stig_settings` | **`stig_write`** | Partial JSON; any §4.3.1 field except `hec_token` | Updated public object. Unmentioned fields are preserved. `hec_token` in the body is ignored. |

**GET response fields:** `_key` (always `general`), `vim_mode`, `trust_event_collection_id`, `ingest_index`, `ingest_sourcetype`, `hec_url`, `reconcile_earliest`, `updated_at`, `updated_by`. Missing conf values use defaults from `models.py`.

**Typical callers:** STIG Editor (`vim_mode` only), classic **Editor shortcuts** view, automation scripts with **`stig_write`**. Full-form edits should use the UCC **Configuration** page so Splunk audits conf changes.

### 11.8 Ingest assignment and setup readiness

**Assignment** — global KV tables and REST documented in §7.8–7.9. Ingest resolution order when `trust_event_collection_id` is false: host×baseline **override** → first matching **rule** → Default workspace; when true, honor event `collectionId` before rules (legacy Watcher).

**Readiness** — onboarding checks for Splunk roles, HEC input, app filesystem ownership, and `install.is_configured`:

| Method | Path | Capability | Body | Response |
|--------|------|------------|------|----------|
| GET | `/stig_readiness` | Authenticated (no extra STIG cap) | — | `{roles, hec, ownership, is_configured, documentation_view, platform_ready, can_stig_write, can_stig_admin}` |
| POST | `/stig_readiness` | Splunk **`admin`** / **`sc_admin`** or **`stig_admin`** | `{"action": "complete"}` | Marks `local/app.conf` `[install] is_configured = 1` when ownership checks pass |

---

## 12. Splunk Search (reporting)

**Do not** rely on `| rest .../storage/collections/data/...` for reviews: that endpoint returns a **flat JSON array**, not Splunk REST `entry[]`, so typical `rest` + `spath` patterns return **zero rows**.

**Do** use kvstore lookups from `transforms.conf` with app context **`stigs_in_splunk`**.

**ACL note:** KV `inputlookup` stanzas (including `stig_collections`) return rows for **all** workspaces in the collection. They are **not** filtered by workspace grants or REST `access_principals`. Any Splunk user who can run searches against this app can read lookup fields (for example workspace `name` and `metadata`). Use persist **`/stig_*` REST** when grant-scoped access is required.

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

Workspace metadata (REST `GET/PATCH .../metadata` stores JSON in KV; lookup exposes the raw string column):

```spl
| inputlookup stig_collections
| eval metadata=coalesce(metadata, "{}")
| search metadata="*moderate*"
| table _key name description metadata
```

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

**Indexed audit (optional but shipped):** the same mutations also emit JSON events to index **`stig_audit`** with sourcetype **`stig:audit`** via the app HTTP input `stig_audit` (HEC) or `/services/receivers/simple` during authenticated REST. If the index or input is unavailable, only splunkd logging occurs. Event fields include `action`, `user`, `entity_type`, `entity_id`, `object`, `workspace_id`, `details`, and `time`. Admin setup: [docs/audit-index.md](docs/audit-index.md). Splunk Web dashboard **`stig_audit_dashboard`** (nav **Audit**) lists recent actions.

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
| `test_splunk_kvstore` | All shipped collection stanzas exist; direct KV insert/read |
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
  -d '{"status":"open","finding_details":"Example finding","comments":"Example"}'

# 6 Export CKLB
curl $AUTH "$BASE/stig_checklists/CHECKLIST_ID/export?format=cklb"
```

---

## 17. Known limitations

| Limitation | Detail |
|------------|--------|
| Orphan data | Failed imports before KV `_key` fix may leave orphan `stig_baseline_rules` or empty baselines; no automatic GC. Admins can report and delete orphan **rules** via `GET/POST /stig_baselines/gc_orphan_rules` (does not remove empty baseline headers or checklist/review rows). |
| No baseline dedup for legacy rows | Missing `content_fingerprint` until re-import. |
| Baseline catalog | Default catalog is global; optional per-workspace rows via `stig_collection_id` (§7.3). |
| Collection delete | Blocked when children exist unless `?cascade=true`; cascades workspace hosts/checklists/reviews/grants/review history and **assignment rules/overrides targeting that workspace**; global baselines unchanged. UCC Configuration delete only allows empty workspaces. |
| Export review join | By `group_id` primarily; empty `group_id` in XCCDF may weaken CKL/CKLB status linkage for some rules. |
| Batch rule insert | Sequential inserts via `batch_save`; large STIGs (~366 rules) take seconds. |
| Review history at scale | Workspace timeline loads all KV rows then filters in-process (§7.7). |
| Search lookups | `inputlookup` on KV stanzas is not grant-filtered (§12). |
| No RMF package entity | Governance grouping is workspace + labels today; `stig_reviews.package_id` is Evaluate-STIG/CKLB only (§7.6, §20). |

---

## 18. Regression smoke criteria

Use after releases or large changes (not a greenfield build checklist):

1. App mounts in Splunk 10; all §6.1 KV collections exist after install/restart.
2. Custom REST CRUD and documented nested routes (`import`, `export`, `rules`, reporting, grants, labels) respond.
3. XCCDF import dedupes by `content_fingerprint` (**200** + `deduplicated` on repeat).
4. Checklist create spawns one `not_reviewed` review per baseline rule.
5. Review PATCH + export round-trip CKLB/CKL status.
6. Workspace `access_principals` / grants hide hosts/checklists/reviews from unauthorized users.
7. `| inputlookup stig_reviews` returns rows with app context.
8. Offline unit tests pass; Splunk integration tests pass when available.
9. UCC **Configuration** saves workspaces, baseline list/delete, and Editor & ingest settings without exposing `hec_token`.

---

## 19. Phase 2 backlog (preserve intent)

- Ingested findings → CIM / macros / dashboards.
- RMF packages (authorization labels) — **proposed** requirements in §20.
- KV cleanup jobs beyond orphan-rule GC; stronger cross-entity consistency transactions.

---

## 20. Proposed: RMF packages (not implemented)

**Status:** Product request only — **no** RMF package collection, REST, or UI in the repo today. Do **not** reuse or overload `stig_reviews.package_id` (that field remains the **Evaluate-STIG / CKLB package id**, §7.6).

RMF packages are **labels** for now (organizational authorization boundary). Each has a **name** and an **id**. REST/KV shapes are out of scope here; the decisions below are product rules for a future implementation.

### 20.1 Decisions

| Topic | Decision |
|-------|----------|
| Workspace scope | An RMF package **may span workspaces** (not limited to a single `stig_collection`). |
| Where stored | The package is stored on the **host + baseline** combination (checklist binding). **Findings inherit** it; reviews are **not** tagged one-by-one with an RMF package id. |
| Unassigned | Rows with no package belong to the system **Unassigned** package: **name** `unassigned`, **id** `-1` (string). **Not deletable.** |
| Bulk assign | **Bulk reassignment** is by **host/baseline combo** (not per-review). |
| Host default | A **host** may have a **default** RMF package. The default is **one global choice per hostname** (same hostname across all workspaces shares one default). Baselines on that host **inherit** the default unless a **host/baseline combo** has an **explicit** package assignment — **explicit combo wins**. Typical case: one host → one package; a rare split across baselines on the same host remains possible. |
| Uniqueness | A **host + baseline** combination may exist in **only one** RMF package (at most one package per pair). |
| Administration | **`stig_admin`**, plus Splunk **`admin`** and **`sc_admin`**, may **create** packages and **assign** them (including in-app bulk assign). **`stig_write`** may **not** create packages. |
| Reporting | **Every** report may run **across all packages** or be **filtered to one package id**: POA&M, in-app findings, HEC, and exports. |
| Identity | Package **id** is **typed in** by an admin, must be **unique within this app**, and **may match** an id used in other Splunk inventory data. **Name** need **not** be unique. |
| Id change | The typed package **id may change** (discouraged). A single **rename** must **bulk-update** every reference: each **host default**, each **host/baseline override**, and any **denormalized finding field** that stored the old id. |

**Finding coverage:** Every finding (compliance sense: assessor review row) is in **exactly one** RMF package via inheritance from its host/baseline (or host default / Unassigned). Implementations may denormalize the effective RMF package id on finding rows for reporting; id renames must rewrite those copies (see **Id change**).

### 20.2 External assignment row contract (spec-owned)

Other Splunk datasets may **push** host/baseline package assignments into this app. Each row:

| Field | Required | Meaning |
|-------|----------|---------|
| `host` | yes | Hostname (global key; same as host default scope). |
| `baseline` | no | When **omitted**, the row sets the **global host default** package for `host`. When **present**, the row sets the **host/baseline override** for that pair. |
| `package_id` | yes | Target RMF package **id** (string). |

Rules:

- **`package_id` must already exist** as a defined RMF package in this app. An unknown id is a **row error**; ingest **does not** auto-create packages.
- **Package creation** remains limited to **`stig_admin`** / Splunk **`admin`** / **`sc_admin`** (not available via this row contract).
- Transport (HEC, `| rest`, saved-search adapter, etc.) is an implementation detail; the **row shape above** is what this spec guarantees.
