#!/usr/bin/env bash
# Fail if metadata/local.meta is present in a built app tree or release tarball.
# Matches splunk-development skill package-check.sh rule (do not ship local.meta).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${1:-$ROOT/output/stigs_in_splunk}"
TGZ="${2:-}"

fail=0
err() { printf 'FAIL  %s\n' "$*" >&2; fail=1; }

if [[ -d "$APP_DIR" ]]; then
  if [[ -f "$APP_DIR/metadata/local.meta" ]]; then
    err "metadata/local.meta is present in $APP_DIR — do not package it"
  fi
else
  err "app directory not found: $APP_DIR"
fi

if [[ -n "$TGZ" ]]; then
  if [[ ! -f "$TGZ" ]]; then
    err "tarball not found: $TGZ"
  elif tar -tzf "$TGZ" | grep -qE '(^|/)metadata/local\.meta$'; then
    err "metadata/local.meta is present in tarball $TGZ — do not package it"
  fi
fi

exit "$fail"
