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
