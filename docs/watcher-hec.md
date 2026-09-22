# STIGMan Watcher HEC event schema

This document describes the **`stig:finding`** JSON events used by `stigs_in_splunk` for checklist ingest, HTTP Event Collector (HEC), and index-to-KV reconcile. The review portion matches what [STIG Manager Watcher](https://github.com/NUWCDIVNPT/stigman-watcher) posts to `POST /collections/{collectionId}/reviews/{assetId}` after parsing CKL/CKLB/XCCDF (via [stig-manager-client-modules](https://github.com/NUWCDIVNPT/stig-manager-client-modules) `reviewsFromCkl` / `reviewsFromCklb` / `reviewsFromXccdf`).

Implementation entry points:

| Component | Location |
|-----------|----------|
| Canonical event builder / normalizer | `package/bin/importers/events.py` |
| Watcher-shaped review helpers | `package/bin/importers/ingest.py` |
| HEC POST | `package/bin/services/hec.py` → input `[http://stig_findings]` |
| KV apply | `package/bin/services/apply.py` |
| Index reconcile | `package/bin/services/reconcile.py`, `\| stigkvreconcile`, saved search **STIG reconcile findings to KV** (every 5 minutes) |
| REST reconcile | `GET\|POST /stig_imports/reconcile` |

---

## HEC envelope

Send one event per rule finding to Splunk HEC (`/services/collector/event`). The app wraps fat events like this when indexing from `POST /stig_imports`:

```json
{
  "time": 1710000000,
  "index": "stig",
  "sourcetype": "stig:finding",
  "source": "stigs_in_splunk",
  "event": { }
}
```

The **`event`** object (or a bare JSON body to HEC with the same fields at the top level) is what `normalize_finding_event()` parses. If the payload nests fields under `event`, optional envelope `time` is copied onto the finding.

Configure index and sourcetype in UCC **Editor & ingest** settings (`ingest_index`, `ingest_sourcetype`; defaults `stig` / `stig:finding`). The HEC token is stored only on the Splunk `stig_findings` HTTP input, not in the UI.

---

## Watcher POST review fields (required for KV apply)

These are the properties Watcher sends per review (Splunk **slim** events use the same top-level names):

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `ruleId` | yes* | string | DISA rule id (≤ 45 chars), e.g. `SV-12345r1_rule`. *Or match via `groupId` only if no rule id. |
| `groupId` | no | string | V-id (`V-12345`). CKL parser in this app adds it; Watcher CKL reviews may omit it. Used for dedupe keys and review seed lookup. |
| `result` | yes | string | Watcher enum: `pass`, `fail`, `notapplicable`, `notchecked` (and scan variants mapped to these). |
| `detail` | no | string | Finding details (CKL `FINDING_DETAILS`). Aliases: `finding_details`. |
| `comment` | no | string | Assessor comment (CKL `COMMENTS`). Aliases: `comments`. |
| `status` | no | string | STIG Manager workflow label on ingest, e.g. `saved`, `submitted`, `accepted`. Default `saved` when absent. |
| `resultEngine` | no | object | Evaluate-STIG / SCAP provenance (product, version, time, `checkContent`, `overrides`, …). Stored on host `metadata.ingest`. |

**Result → KV review status** (via `status_from_result` / `RESULT_TO_STATUS`):

| `result` | KV `status` |
|----------|-------------|
| `pass` | `not_a_finding` |
| `fail` | `open` |
| `notapplicable` | `not_applicable` |
| `notchecked` | `not_reviewed` |

---

## Splunk finding context (slim + fat)

In addition to the review body, each indexed finding carries **asset + STIG + workspace** context (Watcher resolves these via the STIG Manager API; Splunk embeds them in the event):

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `assetName` | yes | string | Hostname / asset name (CKL `HOST_NAME`, CKLB `target_data.host_name`). |
| `benchmarkId` | yes | string | Logical STIG id (e.g. `RHEL_9_STIG`), not the KV baseline `_key`. `xccdf_mil.disa.stig_benchmark_*` prefixes are stripped on ingest. |
| `collectionId` | no | string | Workspace KV `_key`. Aliases: `stig_collection_id`, `collection_id`. Used when **Trust event collection id** is enabled; otherwise assignment rules / default workspace apply. |
| `collectionName` | no | string | Display name; stored under host `metadata.ingest`. |
| `revisionStr` | no | string | DISA revision string `VxRy` when known. |
| `sourceRef` | no | string | Source file URI or scan id. Aliases: `source_ref`, `source_uri`. HEC `source` defaults to this or app name. |
| `source_product` | no | string | e.g. `stigman-watcher`, `evaluate-stig`, `stigs_in_splunk`. |
| `package_id` | no | string | Evaluate-STIG package id (CKLB `package_id`). Alias: `packageId`. Copied to KV `stig_reviews.package_id`. |
| `time` | no | number | Epoch seconds on the finding (HEC event time). |

Optional Splunk-only hints (ignored by Watcher, safe on HEC):

| Field | Notes |
|-------|-------|
| `hostId`, `checklistId`, `baselineId` | KV `_key` hints when re-indexing from an existing deployment. |

### Fat event extensions (`asset`, `stig`, `rule`)

`POST /stig_imports` and the HEC simulator emit **fat** events so the index can rebuild CKL/CKLB exports without re-reading the original file:

- **`asset`** — Watcher `target` plus CKLB-shaped **`target_data`** (`host_name`, `ip_address`, `role`, …).
- **`stig`** — Baseline metadata (`stig_id`, `title`, `version`, `release_info`, …). See `EXPORT_STIG_FIELDS` in `events.py`.
- **`rule`** — Full rule body (`rule_title`, `check_content`, `fix_text`, `ccis`, `check_content_hash`, …). See `EXPORT_RULE_FIELDS` in `events.py`.

Slim senders may omit `asset` / `stig` / `rule` if the baseline already exists in the global catalog (or workspace default resolves it). Otherwise apply fails with `no baseline for … and event has no rule body`.

---

## Examples

### Slim (Watcher-compatible HEC)

Minimal payload a Watcher-equivalent sender can POST to HEC (same fields Watcher posts per review, plus Splunk routing context):

```json
{
  "collectionId": "507f1f77bcf86cd799439011",
  "assetName": "web-01.example.mil",
  "benchmarkId": "Example_STIG",
  "ruleId": "SV-000001r1_rule",
  "groupId": "V-000001",
  "result": "fail",
  "detail": "sshd permits root login",
  "comment": "remediate next window",
  "status": "saved",
  "source_product": "stigman-watcher",
  "sourceRef": "watcher://path/host.ckl",
  "package_id": "100001",
  "resultEngine": {
    "type": "script",
    "product": "Evaluate-STIG",
    "version": "1.2507.1"
  }
}
```

### Fat (app import / simulator)

After `POST /stig_imports?format=ckl`, each indexed event also includes nested `asset`, `stig`, and `rule` objects (see `build_finding_event()` and `tests/test_checklist_ingest.py::test_fat_hec_event_can_rebuild_checklist`).

---

## Dedupe and ordering

Within one reconcile run, events are grouped by host + benchmark, then deduplicated by **`finding_key`**:

```
collectionId | assetName (casefold) | benchmarkId (casefold) | ruleId or groupId
```

Later events in the same batch overwrite earlier ones for the same key. The scheduled search sorts index results by `_time` ascending so the **latest** finding wins when replaying a time window.

---

## How reconcile applies events to KV

Applies to **`POST /stig_imports/reconcile`**, **`| stigkvreconcile`**, and the direct KV path inside **`POST /stig_imports`** (same `apply_finding_events()` logic):

1. **`normalize_finding_event`** — unwrap HEC envelope, coerce aliases, fill defaults, compute `_status` and `_key`.
2. **Workspace resolution** — `collectionId` (if trusted), assignment rules (match on hostname, benchmark, `source_product`, `package_id`, …), host×baseline overrides, else **Default** workspace.
3. **Host** — create or update `stig_hosts` from `asset` / `assetName` (IP, FQDN, MAC, role, `metadata.ingest`).
4. **Baseline** — import from fat `stig`+`rule` bodies if needed, else resolve existing baseline via `benchmarkId` / workspace default.
5. **Checklist** — ensure host + baseline checklist exists; merge `target_data` from fat events.
6. **Reviews** — patch matching `stig_reviews` from `detail`, `comment`, `result`→`status`, optional `package_id`.

**Override policy:** incoming findings are authoritative and overwrite draft review content unless the KV row has **`ingest_lock: true`**. Ingest never sets `ingest_lock`. Non-draft workflow states follow the same rules as REST PATCH (see `review_workflow.py`).

**Configuration:**

| Setting | Effect |
|---------|--------|
| `reconcile_earliest` | SPL earliest time for scheduled reconcile (default `-15m`; saved search also sets `dispatch.earliest_time`). |
| `trust_event_collection_id` | When true, honor `collectionId` on the event before assignment rules. |

---

## Field mapping reference (Watcher → Splunk KV)

| Watcher / event field | KV / behavior |
|----------------------|---------------|
| `assetName` | `stig_hosts.hostname` |
| `asset` / `target_data` | `stig_checklists.target_data`, host fields |
| `benchmarkId` / `stig.stig_id` | Resolve `stig_baselines` by logical STIG id |
| `ruleId` / `groupId` | Match `stig_reviews` via rule seeds |
| `detail` | `stig_reviews.finding_details` |
| `comment` | `stig_reviews.comments` |
| `result` | `stig_reviews.status` (mapped) |
| `package_id` | `stig_reviews.package_id` |
| `source_product`, `sourceRef`, `collectionName`, `resultEngine` | `stig_hosts.metadata.ingest` |

---

## Testing and simulation

- Unit tests: `tests/test_slim_hec_apply.py`, `tests/test_watcher_hec_schema.py`, `tests/test_checklist_ingest.py`.
- HEC simulator: `tools/hec_simulator/` (builds fat Watcher-shaped events from XCCDF fixtures).
- Manual reconcile: see [README.md](../README.md#reconcile-indexed-findings-into-kv-same-job-as-the-5-minute-saved-search).

---

## Related STIG Manager API

Watcher ultimately calls STIG Manager REST; this app does **not** expose the same URLs. For behavioral reference only:

- Batch review POST shape: OpenAPI `Review` result objects (`ruleId`, `result`, `detail`, `comment`, `status`, `resultEngine`, …) in [stig-manager.yaml](https://github.com/NUWCDIVNPT/stig-manager/blob/main/api/source/specification/stig-manager.yaml).
- Splunk persist API: [spec.md](../spec.md) §11.4.1.
