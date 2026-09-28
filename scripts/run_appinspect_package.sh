#!/usr/bin/env bash
# Offline AppInspect for the release tarball (no Splunk, no API token).
# Fails the build on AppInspect error severity (CLI exit 1/2/3).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TGZ="${1:-}"
if [[ -z "$TGZ" ]]; then
  TGZ="$(ls -t "$ROOT/output"/stigs_in_splunk-*.tar.gz 2>/dev/null | head -1 || true)"
fi
[[ -n "$TGZ" && -f "$TGZ" ]] || {
  echo "Usage: $0 [path/to/stigs_in_splunk-*.tar.gz]" >&2
  echo "No release tarball found under $ROOT/output/" >&2
  exit 1
}

APPINSPECT="${APPINSPECT:-$ROOT/.venv-ucc/bin/splunk-appinspect}"
if [[ ! -x "$APPINSPECT" ]]; then
  APPINSPECT="$(command -v splunk-appinspect 2>/dev/null || true)"
fi
[[ -n "$APPINSPECT" && -x "$APPINSPECT" ]] || {
  echo "ERROR: splunk-appinspect not found. Install into .venv-ucc:" >&2
  echo "  .venv-ucc/bin/pip install splunk-appinspect" >&2
  exit 1
}

# Tag `cloud`: offline CLI checks without Splunkbase API credentials.
# Fail on AppInspect *error* severity (CLI exit 1/2/3), not on failure/warning.
INSPECT_CMD=(
  "$APPINSPECT" inspect "$TGZ"
  --included-tags cloud
)

printf 'Running: %q ' "${INSPECT_CMD[@]}"
echo
"${INSPECT_CMD[@]}"
