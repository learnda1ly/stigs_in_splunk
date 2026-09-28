#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UCC_GEN="${UCC_GEN:-$ROOT/.venv-ucc/bin/ucc-gen}"
UCC_PYTHON="${UCC_PYTHON:-$ROOT/.venv-ucc/bin/python}"
BUILT="$ROOT/output/stigs_in_splunk"

if [[ ! -f "$BUILT/app.manifest" ]]; then
  "$ROOT/scripts/build_ucc.sh"
fi

cd "$ROOT"
"$UCC_PYTHON" -c "from additional_packaging import strip_ship_tree; strip_ship_tree('${BUILT}')"

PACKAGE_CHECK="$ROOT/.cursor/skills/splunk-development/scripts/package-check.sh"
"$PACKAGE_CHECK" "$BUILT"

"$UCC_GEN" package --path "$BUILT" -o "$ROOT/output"
echo "Package written under $ROOT/output/"
