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
