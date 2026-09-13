#!/usr/bin/env bash
# Run Splunk integration tests against a local instance.
#
# Usage:
#   export SPLUNK_PASSWORD='your-admin-password'
#   ./scripts/run_splunk_tests.sh
#
# Optional:
#   SPLUNK_HOST=127.0.0.1 SPLUNK_PORT=8089 SPLUNK_USERNAME=admin

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "${SPLUNK_PASSWORD:-}" ]]; then
  echo "SPLUNK_PASSWORD is not set; running unit tests only (integration tests will skip)." >&2
  exec python3 -m unittest discover -s "${ROOT}/tests" -p 'test_*.py' -v
fi

export SPLUNK_INTEGRATION=1
export SPLUNK_HOST="${SPLUNK_HOST:-127.0.0.1}"
export SPLUNK_PORT="${SPLUNK_PORT:-8089}"
export SPLUNK_USERNAME="${SPLUNK_USERNAME:-admin}"

if ! mountpoint -q "${SPLUNK_HOME:-/opt/splunk}/etc/apps/stigs_in_splunk" 2>/dev/null; then
  echo "Tip: mount the app first with ${ROOT}/scripts/link-splunk-app.sh" >&2
fi

python3 -m unittest discover -s "${ROOT}/tests" -p 'test_*.py' -v
