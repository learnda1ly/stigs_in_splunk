#!/usr/bin/env bash
# Build installable Splunk app with Splunk UCC (ucc-gen).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UCC_GEN="${UCC_GEN:-$ROOT/.venv-ucc/bin/ucc-gen}"
UCC_PYTHON="${UCC_PYTHON:-$ROOT/.venv-ucc/bin/python}"
TA_VERSION="${TA_VERSION:-0.1.0}"
if [[ ! -x "$UCC_GEN" ]]; then
  echo "ucc-gen not found. Create venv and install:" >&2
  echo "  python3 -m venv .venv-ucc && .venv-ucc/bin/pip install 'splunk-add-on-ucc-framework>=5.68'" >&2
  echo "Install from PyPI (not GitHub). The git checkout does not ship the prebuilt UCC UI." >&2
  exit 1
fi

OUTPUT="${UCC_OUTPUT:-$ROOT/output}"
mkdir -p "$OUTPUT"
rm -rf "$OUTPUT/stigs_in_splunk"

if [[ "${SKIP_UI_BUILD:-}" != "1" ]]; then
  "$ROOT/scripts/build_ui.sh"
fi

"$UCC_GEN" build \
  --source "$ROOT/package" \
  --config "$ROOT/globalConfig.yaml" \
  --output "$OUTPUT" \
  --ta-version "$TA_VERSION" \
  --python-binary-name "$UCC_PYTHON" \
  "$@"

echo "Built app: $OUTPUT/stigs_in_splunk"

ENTRY_JS="$OUTPUT/stigs_in_splunk/appserver/static/js/build/entry_page.js"
GLOBAL_JSON="$OUTPUT/stigs_in_splunk/appserver/static/js/build/globalConfig.json"
if [[ ! -f "$ENTRY_JS" ]]; then
  echo "ERROR: missing $ENTRY_JS" >&2
  echo "Install UCC from PyPI so the prebuilt configuration UI is included:" >&2
  echo "  .venv-ucc/bin/pip install --force-reinstall 'splunk-add-on-ucc-framework>=5.68'" >&2
  exit 1
fi
if [[ ! -f "$GLOBAL_JSON" ]]; then
  echo "ERROR: missing $GLOBAL_JSON (UCC Configuration page will be blank)" >&2
  exit 1
fi
python3 -c "import json,sys; json.load(open(sys.argv[1])); print('globalConfig.json ok')" "$GLOBAL_JSON"

UCC_LIB="$OUTPUT/stigs_in_splunk/lib"
if [[ ! -d "$UCC_LIB/splunktaucclib" ]]; then
  echo "ERROR: splunktaucclib missing from $UCC_LIB" >&2
  echo "Add splunktaucclib>=6.6.0,<8 and solnlib>=5.5.0,<8 to package/lib/requirements.txt and rebuild." >&2
  exit 1
fi
PYTHONPATH="$UCC_LIB" "$UCC_PYTHON" -c "from splunktaucclib.rest_handler.admin_external import AdminExternalHandler; print('splunktaucclib ok')"

APP_MOUNT="${SPLUNK_HOME:-/opt/splunk}/etc/apps/stigs_in_splunk"
if mountpoint -q "$APP_MOUNT" 2>/dev/null; then
  src="$(findmnt -n -o SOURCE "$APP_MOUNT" 2>/dev/null || true)"
  if [[ "$src" == *deleted* ]]; then
    echo "WARNING: Splunk still bind-mounts a deleted output directory." >&2
    echo "Remount before using the UI:" >&2
    echo "  ./scripts/link-splunk-app.sh umount && ./scripts/link-splunk-app.sh" >&2
    echo "  sudo systemctl restart Splunkd" >&2
  fi
fi
