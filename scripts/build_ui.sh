#!/usr/bin/env bash
# Build SplunkUI (React) pages into package/appserver/static/ui/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/ui"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build
echo "Built SplunkUI bundles into package/appserver/static/ui/"
if rg -l '\.\./appserver/static/ui' "$ROOT/package/appserver/static"/stig_*_ui.js 2>/dev/null; then
  echo "ERROR: legacy stig_*_ui.js loaders must not use ../appserver paths; use stig_splunk_ui_boot.js in views." >&2
  exit 1
fi
