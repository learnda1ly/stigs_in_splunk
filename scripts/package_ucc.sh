#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UCC_GEN="${UCC_GEN:-$ROOT/.venv-ucc/bin/ucc-gen}"
BUILT="$ROOT/output/stigs_in_splunk"

if [[ ! -f "$BUILT/app.manifest" ]]; then
  "$ROOT/scripts/build_ucc.sh"
fi

"$UCC_GEN" package --path "$BUILT" -o "$ROOT/output"
echo "Package written under $ROOT/output/"
