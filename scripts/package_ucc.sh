#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UCC_GEN="${UCC_GEN:-$ROOT/.venv-ucc/bin/ucc-gen}"
BUILT="$ROOT/output/stigs_in_splunk"

if [[ ! -f "$BUILT/app.manifest" ]]; then
  "$ROOT/scripts/build_ucc.sh"
fi

"$ROOT/scripts/check_package_no_local_meta.sh" "$BUILT"

"$UCC_GEN" package --path "$BUILT" -o "$ROOT/output"

TGZ="$(ls -t "$ROOT/output"/stigs_in_splunk-*.tar.gz 2>/dev/null | head -1 || true)"
if [[ -z "$TGZ" || ! -f "$TGZ" ]]; then
  echo "ERROR: expected tarball under $ROOT/output/" >&2
  exit 1
fi
"$ROOT/scripts/check_package_no_local_meta.sh" "$BUILT" "$TGZ"

echo "Package written: $TGZ"
