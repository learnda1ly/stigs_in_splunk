# Automation guide (Evaluate-STIG, OpenSCAP, REST)

Use this guide to push **scan results** and **checklists** into `stigs_in_splunk` without Splunk Web. It complements the curl examples in [README.md](../README.md) and the machine-readable contract in [openapi.yaml](openapi.yaml) (human index [api.md](api.md)).

## Prerequisites

1. **Splunk auth** — Management port (`8089`): HTTP Basic (`-u user:pass`) or a valid Splunk session token. Requires capabilities `stig_read` / `stig_write` (and `stig_admin` for deletes). See [api.md — Authentication](api.md#authentication).
2. **Baseline catalog** — Import the matching Manual STIG revision (`POST /stig_baselines/import`) or set a workspace [default revision](api.md) before XCCDF results ingest resolves rules.
3. **Workspace** — Pass `stig_collection_id` on imports, or omit it to use the **Default** workspace.

Base URL (paths below are relative):

```text
https://<host>:8089/servicesNS/nobody/stigs_in_splunk
```

## API contract and versioning

- **OpenAPI 3:** [docs/openapi.yaml](openapi.yaml) lists persist `/stig_*` routes, query parameters (including `format=` on `/stig_imports`), and indicative response shapes.
- **Versioning:** App version in `package/app.manifest` tracks `info.version` in the OpenAPI file. There is no URL version prefix; breaking REST changes should bump the app minor version and appear in release notes. Details: [api.md — Versioning](api.md#versioning).

**Not in scope for this port:** STIG Manager URL literals, OAuth scopes, or a generated client SDK. For authoritative KV field shapes, use [spec.md](../spec.md) and live `GET` responses.

## Path A — REST file ingest (`POST /stig_imports`)

Best when automation already has **CKL/CKLB**, a **zip** of checklists, or **XCCDF `TestResult`** XML on disk.

| Goal | `format` query | Body |
|------|----------------|------|
| Single OpenSCAP / Evaluate-STIG results file | `xccdf-results` | Raw XML (`TestResult` root or embedded) |
| Zip of `*-results.xml` (nested zips OK) | `xccdf-results-zip` | Raw zip bytes |
| Mixed checklist + scan zip | `zip` | Raw zip bytes |
| Single CKL or CKLB | `ckl` / `cklb` | Raw file bytes |

Query parameters (see OpenAPI): `source_uri` (logical name for audit/HEC), `stig_collection_id` (optional).

### curl — single XCCDF results file

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=xccdf-results&stig_collection_id=COLLECTION_ID&source_uri=host-results.xml" \
  --data-binary @/path/to/openscap-results.xml
```

### curl — Evaluate-STIG / OpenSCAP results archive

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=xccdf-results-zip&stig_collection_id=COLLECTION_ID&source_uri=scan-results.zip" \
  --data-binary @scan-results.zip
```

Supported XML: XCCDF 1.2 `TestResult` with `rule-result` children (typical OpenSCAP `*-results.xml` or Evaluate-STIG output). **Not supported:** ingesting full SCAP source data stream bundles as one artifact — import Manual STIG baselines via `/stig_baselines` instead.

`POST /stig_imports` indexes **`stig:finding`** events (when HEC is configured) and applies reviews to KV in the same request. Re-import updates existing host + STIG rows unless a review has `ingest_lock`.

### Python — session token (management port)

```python
import requests

BASE = "https://localhost:8089/servicesNS/nobody/stigs_in_splunk"
session = requests.Session()
session.verify = False  # lab only
session.auth = ("admin", "changeme")

with open("host-results.xml", "rb") as f:
    r = session.post(
        f"{BASE}/stig_imports",
        params={
            "format": "xccdf-results",
            "stig_collection_id": "COLLECTION_ID",
            "source_uri": "host-results.xml",
        },
        data=f,
    )
r.raise_for_status()
print(r.json())
```

Use `requests` with Basic auth as above, or obtain a Splunk session token via `/services/auth/login` and pass `Authorization: Splunk <token>`.

### Collection batch import

For many CKL/CKLB files in one call, use `POST /stig_collections/{id}/imports` with JSON `files[]` (per-file `content`, `format`, `source_uri`). See [README.md](../README.md) and OpenAPI path `/stig_collections/{collectionId}/imports`.

## Path B — HEC `stig:finding` (Watcher-shaped)

Use when a scanner agent already posts **one event per rule** (same shape as [STIGMan Watcher](https://github.com/NUWCDIVNPT/stigman-watcher)):

1. Configure Splunk HEC input **`stig_findings`** and index/sourcetype in UCC **Editor & ingest** (`ingest_index`, `ingest_sourcetype`; default `stig` / `stig:finding`).
2. POST JSON to `https://<host>:8088/services/collector/event` with `Authorization: Splunk <hec_token>`.
3. Let KV catch up via **`POST /stig_imports/reconcile`** or the scheduled **STIG reconcile findings to KV** search (`| stigkvreconcile`).

Field-level schema, `result` → review status mapping, and fat vs slim events: **[watcher-hec.md](watcher-hec.md)**.

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports/reconcile?earliest=-15m"
```

## After ingest — automation-friendly reads

| Task | REST |
|------|------|
| Workspace metrics | `GET /stig_collections/{id}/metrics` |
| Open findings report | `GET /stig_collections/{id}/findings` or `GET /stig_findings?stig_collection_id=` |
| POA&M export | `GET /stig_collections/{id}/poam?format=csv` |
| Bulk review update | `POST /stig_reviews/batch` |

Grant-based workspace ACLs apply to all of the above; restricted users only see allowed hosts and checklists.

## Evaluate-STIG notes

- Map scan output to **`format=xccdf-results`** or **`xccdf-results-zip`** when the artifact is XCCDF `TestResult` XML.
- Optional `resultEngine` and `source_product` on HEC events are stored for provenance (see [watcher-hec.md](watcher-hec.md)).
- There is no separate “Evaluate-STIG API” in this app — automation uses Splunk persist REST and/or HEC as documented here and in [FEATURE_PARITY.md](FEATURE_PARITY.md).
