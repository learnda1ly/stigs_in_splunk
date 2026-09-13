#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pip install -r "${ROOT}/requirements.txt" -t "${ROOT}/lib" --upgrade
echo "Vendored splunk-sdk into ${ROOT}/lib"
