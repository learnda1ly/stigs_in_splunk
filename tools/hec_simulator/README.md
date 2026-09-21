# HEC STIG finding simulator

Posts **STIG Manager Watcher**-shaped `stig:finding` events to Splunk HTTP Event Collector, using DISA XCCDF baselines from `tests/fixtures/baselines/` (see `manifest.yaml`).

Runs **outside** Splunk; no `splunk` Python module is required.

## Prerequisites

- Python 3.10+
- `pip install pyyaml` (also used by repo packaging scripts)
- Baseline XML: run from repo root:

  ```bash
  chmod +x scripts/download_baseline_fixtures.sh
  ./scripts/download_baseline_fixtures.sh
  ```

  If DISA downloads fail, use the bundled `tests/fixtures/minimal_benchmark.xml` via `--baseline-key minimal` (see below). Unit tests only need the minimal fixture.

- A Splunk HEC token with access to the `stig` index (or your configured index).

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SPLUNK_HEC_URL` | `https://localhost:8088/services/collector/event` | HEC `/services/collector/event` URL |
| `SPLUNK_HEC_TOKEN` | *(required to POST)* | HEC token |
| `STIG_COLLECTION_ID` | *(required)* | Splunk app collection `_key` embedded in each finding |
| `SPLUNK_HEC_INDEX` | `stig` | HEC index (matches app default) |
| `SPLUNK_HEC_SOURCETYPE` | `stig:finding` | Sourcetype (matches app default) |
| `SPLUNK_HEC_SOURCE` | `stigs_in_splunk` | HEC `source` field |

Optional per-host `collection_id` in `hosts.yaml` overrides `STIG_COLLECTION_ID` for that host only.

## Configuration

- **`hosts.yaml`** — six hosts with `hostname`, `ip`, `baseline_key`, and `package_id` (`100001`–`100006`).
- **`tests/fixtures/baselines/manifest.yaml`** — baseline metadata and download URLs.

Event bodies are built with `importers.events.build_finding_event` (`PYTHONPATH=package/bin`) and `source_product=stigman-watcher`. Each rule gets a deterministic pseudo-random `pass` / `fail` / `notapplicable` / `notchecked` result.

## Usage

From the repository root:

```bash
export SPLUNK_HEC_TOKEN='...'
export STIG_COLLECTION_ID='your_collection_key'

# One-shot simulation (all hosts, all rules in each baseline)
python -m tools.hec_simulator run --once

# Smoke run using only the small bundled benchmark for every host
python -m tools.hec_simulator run --once --baseline-key minimal --dry-run

# Periodic simulation every 5 minutes
python -m tools.hec_simulator run --interval 300
```

## Manual baseline download

If `scripts/download_baseline_fixtures.sh` fails (cyber.mil blocked, TLS, or zip name drift):

1. Open each `zip_url` in `tests/fixtures/baselines/manifest.yaml` in a browser.
2. Extract the `*Manual-xccdf.xml` member from each zip.
3. Save it under `tests/fixtures/baselines/` using the `local_file` name from the manifest.

## Tests

```bash
python -m unittest tests.test_hec_simulator -v
```
