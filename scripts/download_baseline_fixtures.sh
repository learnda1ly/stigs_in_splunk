#!/usr/bin/env bash
# Fetch DISA STIG zips listed in tests/fixtures/baselines/manifest.yaml and extract Manual-xccdf.xml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${ROOT}/tests/fixtures/baselines/manifest.yaml"
OUT_DIR="${ROOT}/tests/fixtures/baselines"
CACHE_DIR="${OUT_DIR}/.cache"

mkdir -p "${OUT_DIR}" "${CACHE_DIR}"

exec python3 - "${MANIFEST}" "${OUT_DIR}" "${CACHE_DIR}" <<'PY'
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)

manifest_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
cache_dir = Path(sys.argv[3])

data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
baselines = data.get("baselines") or {}

def find_xccdf_member(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    for prefer in ("Manual-xccdf.xml", "xccdf.xml", "-xccdf.xml"):
        for name in names:
            if name.lower().endswith(".xml") and prefer.lower() in name.lower():
                return name
    for name in names:
        if name.lower().endswith(".xml") and "xccdf" in name.lower():
            return name
    raise FileNotFoundError(f"No XCCDF in zip (sample: {names[:5]})")

failed = []
for key, entry in baselines.items():
    if entry.get("bundled"):
        rel = entry.get("local_file") or ""
        target = (manifest_path.parent / rel).resolve()
        if target.is_file():
            print(f"[ok] bundled {key}: {target.name}")
        else:
            print(f"[skip] bundled {key}: missing {target}")
        continue
    url = (entry.get("zip_url") or "").strip()
    local_name = (entry.get("local_file") or "").strip()
    if not url or not local_name:
        print(f"[skip] {key}: no zip_url/local_file")
        continue
    dest = out_dir / local_name
    if dest.is_file():
        print(f"[ok] {key}: already have {local_name}")
        continue
    zip_name = url.rsplit("/", 1)[-1]
    zip_path = cache_dir / zip_name
    try:
        print(f"[fetch] {key}: {url}")
        urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            member = find_xccdf_member(zf)
            xml_bytes = zf.read(member)
        sha = entry.get("sha256")
        if sha:
            digest = hashlib.sha256(xml_bytes).hexdigest()
            if digest.lower() != str(sha).lower():
                raise ValueError(f"sha256 mismatch for {key}: {digest}")
        dest.write_bytes(xml_bytes)
        print(f"[write] {key}: {dest} ({len(xml_bytes)} bytes from {member})")
    except Exception as exc:
        print(f"[fail] {key}: {exc}", file=sys.stderr)
        failed.append(key)

if failed:
    print(
        "\nSome downloads failed. Manual steps:\n"
        "  1. Download each zip_url from tests/fixtures/baselines/manifest.yaml via browser (DISA public site).\n"
        "  2. Extract *Manual-xccdf.xml into tests/fixtures/baselines/ using the manifest local_file name.\n"
        "  3. HEC simulator unit tests only require tests/fixtures/minimal_benchmark.xml.\n"
        f"Failed keys: {', '.join(failed)}",
        file=sys.stderr,
    )
    raise SystemExit(1)
print("All baseline fixtures ready.")
PY
