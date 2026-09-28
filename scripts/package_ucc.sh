#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UCC_GEN="${UCC_GEN:-$ROOT/.venv-ucc/bin/ucc-gen}"
UCC_PYTHON="${UCC_PYTHON:-$ROOT/.venv-ucc/bin/python}"
SLIM="${SLIM:-$ROOT/.venv-ucc/bin/slim}"
BUILT="$ROOT/output/stigs_in_splunk"

if [[ ! -f "$BUILT/app.manifest" ]]; then
  "$ROOT/scripts/build_ucc.sh"
fi

"$ROOT/scripts/check_package_no_local_meta.sh" "$BUILT"

cd "$ROOT"
"$UCC_PYTHON" -c "from additional_packaging import strip_ship_tree; strip_ship_tree('${BUILT}')"

PACKAGE_CHECK="$ROOT/.cursor/skills/splunk-development/scripts/package-check.sh"
"$PACKAGE_CHECK" "$BUILT"

"$UCC_GEN" package --path "$BUILT" -o "$ROOT/output"

TGZ="$(ls -t "$ROOT/output"/stigs_in_splunk-*.tar.gz 2>/dev/null | head -1 || true)"
if [[ -z "$TGZ" || ! -f "$TGZ" ]]; then
  echo "ERROR: expected tarball under $ROOT/output/" >&2
  exit 1
fi

"$ROOT/scripts/check_package_no_local_meta.sh" "$BUILT" "$TGZ"

if [[ -x "$SLIM" ]]; then
  "$SLIM" validate "$TGZ"
else
  SLIM_BIN="$(command -v slim 2>/dev/null || true)"
  [[ -n "$SLIM_BIN" ]] || {
    echo "ERROR: slim not found. Install splunk-packaging-toolkit into .venv-ucc." >&2
    exit 1
  }
  "$SLIM_BIN" validate "$TGZ"
fi

"$ROOT/scripts/run_appinspect_package.sh" "$TGZ"
echo "Package written: $TGZ"
