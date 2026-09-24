#!/usr/bin/env bash
# Bind-mount the built (or source) app into Splunk for local development.
#
# Splunk 10.x often ignores symlinked apps under $SPLUNK_HOME/etc/apps; a bind
# mount works reliably.
#
# Usage (requires sudo):
#   ./scripts/build_ucc.sh          # first time / after conf changes
#   ./scripts/link-splunk-app.sh
#   STIG_APP_SOURCE=package ./scripts/link-splunk-app.sh   # Python-only dev (needs app.conf from prior build copied)
#   ./scripts/link-splunk-app.sh umount

set -euo pipefail

SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
APP_NAME="stigs_in_splunk"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${SPLUNK_HOME}/etc/apps/${APP_NAME}"
DEFAULT_SRC="${ROOT}/output/${APP_NAME}"
APP_SRC="${STIG_APP_SOURCE:-$DEFAULT_SRC}"

if [[ "${1:-}" == "umount" ]]; then
  if mountpoint -q "${TARGET}" 2>/dev/null; then
    sudo umount "${TARGET}"
    echo "Unmounted ${TARGET}"
  elif [[ -L "${TARGET}" ]]; then
    sudo rm -f "${TARGET}"
    echo "Removed symlink ${TARGET}"
  else
    echo "Nothing to unmount at ${TARGET}"
  fi
  exit 0
fi

if [[ ! -d "${SPLUNK_HOME}/etc/apps" ]]; then
  echo "Splunk apps dir not found: ${SPLUNK_HOME}/etc/apps" >&2
  exit 1
fi

if [[ ! -f "${APP_SRC}/default/app.conf" ]]; then
  echo "App not found at ${APP_SRC} (missing default/app.conf)." >&2
  echo "Run: ./scripts/build_ucc.sh" >&2
  exit 1
fi

if mountpoint -q "${TARGET}" 2>/dev/null; then
  echo "Already mounted: ${TARGET}"
  mount | grep " on ${TARGET} " || true
  exit 0
fi

if [[ -e "${TARGET}" ]] || [[ -L "${TARGET}" ]]; then
  sudo rm -rf "${TARGET}"
fi

sudo mkdir -p "${TARGET}"
sudo mount --bind "${APP_SRC}" "${TARGET}"

# Splunk (splunk user) must write local/*.conf and metadata/local.meta for UCC
# Configuration saves. A root-owned bind mount breaks that unless these paths
# are owned by splunk.
SPLUNK_USER="${SPLUNK_USER:-splunk}"
if id "${SPLUNK_USER}" &>/dev/null; then
  sudo mkdir -p "${TARGET}/local" "${TARGET}/metadata"
  if [[ ! -f "${TARGET}/metadata/local.meta" ]]; then
    printf '%s\n' '[]' | sudo tee "${TARGET}/metadata/local.meta" >/dev/null
  fi
  sudo chown "${SPLUNK_USER}:${SPLUNK_USER}" \
    "${TARGET}/local" \
    "${TARGET}/metadata" \
    "${TARGET}/metadata/local.meta"
fi

echo "Bind-mounted ${APP_SRC} -> ${TARGET}"
echo "Restart Splunk after handler or config changes."
