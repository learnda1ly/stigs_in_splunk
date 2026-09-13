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

"$UCC_GEN" build \
  --source "$ROOT/package" \
  --config "$ROOT/globalConfig.yaml" \
  --output "$OUTPUT" \
  --ta-version "$TA_VERSION" \
  --python-binary-name "$UCC_PYTHON" \
  "$@"

echo "Built app: $OUTPUT/stigs_in_splunk"
