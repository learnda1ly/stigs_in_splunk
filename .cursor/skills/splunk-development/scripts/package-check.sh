#!/usr/bin/env bash
# Fail a Splunk app source tree for the packaging mistakes AppInspect and
# Cloud vetting reject first. Usage: package-check.sh <app-dir>
set -euo pipefail

APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "Usage: $0 <app-dir>" >&2; exit 2; }

fail=0
warn() { printf 'WARN  %s\n' "$*"; }
err()  { printf 'FAIL  %s\n' "$*"; fail=1; }
ok()   { printf 'OK    %s\n' "$*"; }

APP="$(cd "$APP" && pwd)"
base="$(basename "$APP")"

[[ -f "$APP/default/app.conf" ]] || err "missing default/app.conf"
[[ -f "$APP/metadata/default.meta" ]] || warn "missing metadata/default.meta"
[[ -d "$APP/local" ]] && err "local/ is present — do not package it"
[[ -f "$APP/metadata/local.meta" ]] && err "metadata/local.meta is present — do not package it"
find "$APP" -name '*.pyc' -o -name '*.pyo' -o -name '__pycache__' | grep -q . \
  && err "compiled Python artifacts present" || ok "no compiled Python artifacts"

if [[ -f "$APP/default/app.conf" ]]; then
  if ! grep -qE '^\[id\]' "$APP/default/app.conf"; then
    warn "app.conf has no [id] stanza (required for Cloud / Splunkbase)"
  fi
  if ! grep -qE '^\[launcher\]' "$APP/default/app.conf"; then
    err "app.conf has no [launcher] stanza"
  fi
  if ! grep -qE '^\[package\]' "$APP/default/app.conf"; then
    warn "app.conf has no [package] stanza"
  fi
fi

# Scripted stanzas should declare a Python version.
for conf in commands.conf restmap.conf alert_actions.conf inputs.conf transforms.conf; do
  f="$APP/default/$conf"
  [[ -f "$f" ]] || continue
  if grep -qE 'filename|python\.|script' "$f" && ! grep -qE 'python\.(version|required)' "$f"; then
    warn "$conf looks scripted but declares no python.version / python.required"
  fi
done

find "$APP" -name 'passwords.conf' | grep -q . && err "passwords.conf present — secrets must not ship"
ok "checked $base at $APP"
exit "$fail"
