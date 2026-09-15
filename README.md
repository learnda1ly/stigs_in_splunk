# STIG in Splunk (PoC)

Minimal Splunk app that stores DISA STIG baseline and checklist **review** state in the KV store and exposes a custom REST API.

See [spec.md](spec.md) for the full build specification.

## Build with Splunk UCC

This app is packaged with the [Splunk UCC framework](https://splunk.github.io/addonfactory-ucc-generator/) (`ucc-gen`). Source lives under `package/`; the installable app is produced under `output/stigs_in_splunk`.

### One-time setup

```bash
python3 -m venv .venv-ucc
.venv-ucc/bin/pip install 'splunk-add-on-ucc-framework>=5.68'
```

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

`STIG_APP_SOURCE` defaults to `output/stigs_in_splunk`. Edit Python under `package/bin/` and re-run `./scripts/build_ucc.sh` before restarting Splunk.

### UCC layout

| Path | Role |
|------|------|
| `globalConfig.yaml` | UCC meta (name, version, visibility); no Configuration/Inputs UI pages |
| `package/` | App source copied into the build (`bin/`, `default/*.conf`, `metadata/`, `app.manifest`) |
| `additional_packaging.py` | Post-build: `reload.collections` trigger, prune unused UCC UI stubs |
| `output/stigs_in_splunk/` | Generated `app.conf`, built artifact for Splunk |

Custom REST uses a **persist** handler (`package/bin/stig_rest_handler.py`) and hand-written `restmap.conf` / `web.conf` (UCC does not generate these for conf-only apps).

### STIG Editor (Splunk Web UI)

Default views are **SplunkUI** (React / `@splunk/react-ui`) pages:

- **STIG Editor** — workspace + host filters, finding list, status, details, comments
- **Import Checklists** — drag-and-drop `.ckl` / `.cklb`; findings go to HEC (`stig:finding`) and KV
- **Export Checklists** — CKL / CKLB download, including bulk zip
- **Configuration** — vim shortcuts, HEC index/token, reconcile window

Classic Simple XML + jQuery views remain under the **Classic** nav menu.

Rebuild UI bundles after changing `ui/src`:

```bash
./scripts/build_ui.sh
```

`./scripts/build_ucc.sh` runs that step unless `SKIP_UI_BUILD=1`.

After install, open the app → **STIG Editor**. Choose a workspace, then edit reviews in a split pane. Status saves immediately; finding details and comments require **Write**. Vim keys live in the classic editor (`?` for help).

## Splunk roles

Assign `stig_user` or `stig_admin`, or grant capabilities `stig_read`, `stig_write`, `stig_admin` (see `package/default/authorize.conf`; `role_admin` includes all three for PoC).

## REST base URL

```text
https://<host>:8089/servicesNS/nobody/stigs_in_splunk
```

Resources: `stig_collections`, `stig_hosts`, `stig_baselines`, `stig_checklists`, `stig_reviews`, `stig_imports`.

## Example flow (curl)

See [spec.md](spec.md) §16 for the full curl workflow. Quick baseline import:

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_baselines/import?format=xccdf&source_uri=minimal_benchmark.xml" \
  --data-binary @tests/fixtures/minimal_benchmark.xml
```

Checklist file ingest (indexes `stig:finding` via HEC, then updates KV):

```bash
curl -k -u admin:changeme -X POST \
  "https://localhost:8089/servicesNS/nobody/stigs_in_splunk/stig_imports?format=cklb&stig_collection_id=COLLECTION_ID&source_uri=host.cklb" \
  --data-binary @path/to/host.cklb
```

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
