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
| `globalConfig.yaml` | UCC meta plus Configuration tabs (workspaces, baselines, editor/ingest) |
| `package/` | App source copied into the build (`bin/`, `default/*.conf`, `metadata/`, `app.manifest`) |
| `package/lib/requirements.txt` | `splunktaucclib` for UCC Configuration REST (pip-installed into `output/.../lib`) |
| `additional_packaging.py` | Post-build: KV reload trigger, keep UCC Configuration view, restore custom nav |
| `output/stigs_in_splunk/` | Generated `app.conf`, Configuration REST handlers, built artifact |

Custom REST uses a **persist** handler (`package/bin/stig_rest_handler.py`) and hand-written `restmap.conf` / `web.conf` (UCC does not generate these for conf-only apps).

### STIG Editor (Splunk Web UI)

Default views are **SplunkUI** (React / `@splunk/react-ui`) pages:

- **STIG Editor** — workspace + host filters, finding list, status, details, comments
- **Import** — checklists (`.ckl` / `.cklb` to HEC and KV) and STIG baselines (XCCDF / CKL / CKLB) on one page with tabs
- **Export** — CKL / CKLB download, including bulk zip
- **Configuration** — UCC-generated page for workspaces and editor/HEC settings. The HEC token stays on the Splunk `stig_findings` input and is never returned to the browser.

Classic Simple XML + jQuery views remain under the **Classic** nav menu.

Rebuild UI bundles after changing `ui/src`:

```bash
./scripts/build_ui.sh
```

`./scripts/build_ucc.sh` runs that step unless `SKIP_UI_BUILD=1`.

After install, open the app → **STIG Editor**. Manage workspaces under **Configuration**; import baselines and checklists under **Import**. Choose a workspace, then edit reviews in a split pane. Status saves immediately; finding details and comments require **Write**.

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
