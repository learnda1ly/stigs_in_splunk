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
| ACL | Workspace-scoped access via **`stig_collection.access_principals`** plus Splunk capabilities **`stig_read`**, **`stig_write`**, **`stig_admin`**. |
| Audit | Structured app logging for mutations (username + action + entity id). |
| Packaging | Reproducible builds with [Splunk UCC](https://splunk.github.io/addonfactory-ucc-generator/) (`ucc-gen build` / `package`). |
| Dev UX | Bind-mount **built** app; vendored **Splunk Python SDK** at repo `lib/` for external tests/scripts only. |
| Tests | Offline unit tests (parsers, fingerprint); optional Splunk integration tests (REST + KV). |
| Search | KV lookups in `package/default/transforms.conf` so **`inputlookup`** works in Splunk Search (not raw KV REST in SPL). |

### 1.2 Out of scope (Phase 2 — do not build in PoC)

- [SplunkUI](https://splunkui.splunk.com/) React dashboards.
- Search macros, CIM Vulnerability datamodel, eventtypes for ingested STIG events.
- Full audit **dashboard** (logs only in PoC).
- XCCDF **results** import mapping to review status (pass/fail → open/not_a_finding).
- Review **merge** across STIG revisions when `check_content_hash` matches (design hooks only).
- Cascading delete of hosts/checklists when a **stig_collection** is deleted.
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
globalConfig.yaml          # UCC meta only (conf-only app: no Configuration/Inputs UI)
additional_packaging.py    # post-build hooks (KV reload trigger, UI stub cleanup)
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
  lib/                     # optional requirements.txt for ucc-gen pip (usually empty)
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

### 4.1 UCC conf-only pattern

- **`globalConfig.yaml`** defines `meta` only (`isVisible: true`, `checkForUpdates: false`). No `pages.configuration` or `pages.inputs` — this is a **REST + KV app**, not a modular-input TA.
- UCC **generates** `default/app.conf`, `app.manifest` version fields, `VERSION`, and copies `package/**` into `output/<app>/`.
- UCC **does not** generate `restmap.conf` / `web.conf` without UI pages; those stay in `package/default/` and are copied verbatim.
- **`additional_packaging.py`:** append `[triggers] reload.collections = simple` to generated `app.conf`; delete unused UCC UI XML stubs if present.

### 4.2 Build commands

```bash
python3 -m venv .venv-ucc
.venv-ucc/bin/pip install 'splunk-add-on-ucc-framework>=5.68'
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
| `stig_admin` | DELETE; manage `access_principals` |

Roles:

- **`stig_user`:** `stig_read`, `stig_write`
- **`stig_admin`:** inherits `stig_user`, plus `stig_admin`
- **`role_admin`:** enable all three for PoC admin UX

Map capabilities to HTTP methods in **each** `restmap.conf` stanza (see §7).

### 5.3 REST base URL

```text
https://<host>:8089/servicesNS/nobody/stigs_in_splunk
```

Resources: `stig_collections`, `stig_hosts`, `stig_baselines`, `stig_checklists`, `stig_reviews`, `stig_imports`.

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
| `access_principals` | string | JSON array string, e.g. `["user:alice","role:stig_admin"]`. Empty/missing ⇒ readable by all authenticated users with caps. |
| `created_at`, `updated_at` | time | |
| `created_by`, `updated_by` | string | Splunk username |

### 7.2 `stig_hosts`

| Field | Type | Notes |
|-------|------|--------|
| `_key` | string | |
| `stig_collection_id` | string | FK → workspace |
| `hostname`, `ip_address`, `fqdn`, `mac_address` | string | CKL/CKLB target |
| `role`, `asset_type`, `tech_area` | string | Defaults: `role=None`, `asset_type=Computing` |
| `web_or_database` | bool | Default false |
| `metadata` | string | JSON object string |
| `created_at`, `updated_at`, `created_by`, `updated_by` | | |

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

`POST /stig_baselines/import`

Query parameters (must support Splunk persist **query as list of pairs** — normalize to dict in handler):

| Param | Default | Meaning |
|-------|---------|---------|
| `format` | `xccdf` | `xccdf` \| `cklb` \| `ckl` |
| `source_uri` | `""` | Stored on baseline; not used for dedup |

Body: raw document bytes (XML or JSON). Content-Type: `application/xml` or `application/json`.

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
| GET | `/stig_collections` | — | Array of workspaces user can read |
| POST | `/stig_collections` | JSON `{name, description?, access_principals?}` | **201** created record |
| GET | `/stig_collections/{id}` | — | Record or **404** |
| PATCH/PUT | `/stig_collections/{id}` | Partial JSON | Updated record |
| DELETE | `/stig_collections/{id}` | — | `{deleted: id}`; requires **stig_admin** |

Default `access_principals` on create: `["user:<creator>"]` if omitted.

### 11.2 `stig_hosts`

| Method | Path | Query | Body |
|--------|------|-------|------|
| GET | `/stig_hosts` | `stig_collection_id?` | — |
| POST | `/stig_hosts` | — | `{stig_collection_id, hostname, ip_address?, ...}` |
| GET/PATCH/DELETE | `/stig_hosts/{id}` | — | PATCH fields optional |

DELETE requires **stig_admin**. Writes require workspace **stig_write** access.

### 11.3 `stig_baselines`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_baselines` | List all baseline headers |
| POST | `/stig_baselines/import` | Query `format`, `source_uri`; raw body |
| GET | `/stig_baselines/{id}/rules` | All rules for baseline |

No PATCH/DELETE in PoC.

Import responses:

- **201** new baseline document (KV fields).
- **200** existing baseline + `"deduplicated": true`.

### 11.4 `stig_checklists`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_checklists` | Query `stig_collection_id?` |
| POST | `/stig_checklists` | `{stig_collection_id, host_id, baseline_id, title?, mode?, target_data?}` → spawns reviews |
| GET/PATCH/DELETE | `/stig_checklists/{id}` | DELETE cascades reviews |
| GET | `/stig_checklists/{id}/export` | Query `format=cklb|ckl` |
| POST | `/stig_imports` | Query `format=ckl|cklb`, `source_uri`, `stig_collection_id`; raw CKL/CKLB body |

POST validates: host belongs to workspace; baseline exists; baseline has rules.

### 11.4.1 Checklist file import and HEC ingest

`POST /stig_imports` parses one `.ckl` or `.cklb` the same way [STIG Manager Watcher](https://github.com/NUWCDIVNPT/stigman-watcher) does (`reviewsFromCkl` / `reviewsFromCklb`), then:

1. Emits one **fat** `stig:finding` JSON event per rule to **HEC** (`index=stig`, `sourcetype=stig:finding`). Each event includes Watcher review fields **and** asset `target_data`, STIG metadata, and the rule body (title, check content, fix text, CCIs, hashes) so a CKL/CKLB can be synthesized later from the index + KV.
2. Applies the same events to KV current state (host, baseline, checklist, reviews).

External Evaluate-STIG / Watcher streams must POST the same event shape to the HEC input `[http://stig_findings]`.

`GET|POST /stig_imports/reconcile` (and scheduled search `| stigkvreconcile`) reads recent index events and applies them to KV.

**Override policy:** a matching review is updated from the incoming event (authoritative) unless `ingest_lock` is true on the KV review. Incoming events never set `ingest_lock`.

Requires **`stig_write`**.

### 11.5 `stig_reviews`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/stig_reviews` | Query `checklist_id?`, `status?` |
| GET | `/stig_reviews/{id}` | Single review |
| PATCH/PUT | `/stig_reviews/{id}` | `{status?, finding_details?, comments?, ingest_lock?}` |

Updates require workspace **write** access via parent checklist. Validate `status` against allowed set; accept internal or CKLB status strings on input. `ingest_lock=true` blocks HEC/reconcile from overwriting that finding.

---

## 12. Splunk Search (reporting)

**Do not** rely on `| rest .../storage/collections/data/...` for reviews: that endpoint returns a **flat JSON array**, not Splunk REST `entry[]`, so typical `rest` + `spath` patterns return **zero rows**.

**Do** use kvstore lookups from `transforms.conf` with app context **`stigs_in_splunk`**:

All review rows:

```spl
| inputlookup stig_reviews
| table _key checklist_id group_id rule_id status finding_details comments updated_at
```

Open findings only:

```spl
| inputlookup stig_reviews
| search status=open
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

Actions include: `create`, `update`, `delete`, `import`, `import_deduplicated`.

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
| Collection delete | Does not delete child hosts/checklists. |
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

---

## 19. Phase 2 backlog (preserve intent)

- UCC packaging, SplunkUI management app.
- Ingested findings → CIM / macros / dashboards.
- XCCDF results import; cross-revision review merge using `check_content_hash`.
- Workspace-scoped baselines or sharing model.
- Stronger audit (dedicated index, UI).
- KV cleanup jobs; cascade deletes; bulk review update.
