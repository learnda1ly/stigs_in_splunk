#!/usr/bin/env python3
"""Download RHEL 8 DISA STIG XCCDF, import baseline, create web-01 checklist via REST."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "lib"))

from splunk_client import SplunkRestClient, SplunkRestError  # noqa: E402
from splunk_wait import wait_for_kv  # noqa: E402

# NIST NCP link for RHEL 8 STIG V2R6 (standalone XCCDF in zip)
STIG_ZIP_URL = (
    "https://dl.dod.cyber.mil/wp-content/uploads/stigs/zip/U_RHEL_8_V2R6_STIG.zip"
)


def _find_xccdf_in_zip(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    for prefer in ("Manual-xccdf.xml", "xccdf.xml", "-xccdf.xml"):
        for name in names:
            if name.lower().endswith(".xml") and prefer.lower() in name.lower():
                return name
    for name in names:
        if name.lower().endswith(".xml") and "xccdf" in name.lower():
            return name
    raise FileNotFoundError(f"No XCCDF XML in zip (entries: {names[:10]}...)")


def download_rhel8_xccdf(cache_dir: Path) -> bytes:
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "U_RHEL_8_V2R6_STIG.zip"
    if not zip_path.is_file():
        print(f"Downloading {STIG_ZIP_URL} ...")
        urlretrieve(STIG_ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        member = _find_xccdf_in_zip(zf)
        print(f"Using XCCDF member: {member}")
        return zf.read(member)


def main() -> int:
    password = os.environ.get("SPLUNK_PASSWORD")
    if not password:
        print("Set SPLUNK_PASSWORD", file=sys.stderr)
        return 1

    client = SplunkRestClient.from_env()
    wait_for_kv(client)

    cache = ROOT / "tests" / "fixtures" / "cache"
    xccdf_bytes = download_rhel8_xccdf(cache)

    print("Creating stig_collection...")
    coll = client.post_app_json(
        "stig_collections",
        {
            "name": "RHEL8 Lab",
            "description": "RHEL 8 STIG demo",
            "access_principals": [f"user:{client.username}"],
        },
    )
    collection_id = coll["_key"]
    print(f"  collection_id={collection_id}")

    print("Importing RHEL 8 baseline (may take a minute)...")
    baseline = client.post_app_raw(
        "stig_baselines/import",
        xccdf_bytes,
        content_type="application/xml",
        query={"format": "xccdf", "source_uri": "U_RHEL_8_V2R6_STIG.zip"},
    )
    baseline_id = baseline["_key"]
    rule_count = baseline.get("rule_count")
    print(f"  baseline_id={baseline_id} rule_count={rule_count}")

    print("Creating host web-01...")
    host = client.post_app_json(
        "stig_hosts",
        {
            "stig_collection_id": collection_id,
            "hostname": "web-01",
            "ip_address": "10.0.0.10",
            "fqdn": "web-01.example.com",
            "role": "None",
            "asset_type": "Computing",
        },
    )
    host_id = host["_key"]
    print(f"  host_id={host_id}")

    print("Creating checklist for web-01...")
    checklist = client.post_app_json(
        "stig_checklists",
        {
            "stig_collection_id": collection_id,
            "host_id": host_id,
            "baseline_id": baseline_id,
            "title": "web-01 — RHEL 8 STIG",
        },
    )
    checklist_id = checklist["_key"]
    print(f"  checklist_id={checklist_id}")

    reviews = client.get_app_json("stig_reviews", query={"checklist_id": checklist_id})
    print(f"  reviews spawned: {len(reviews)}")

    summary = {
        "stig_collection_id": collection_id,
        "baseline_id": baseline_id,
        "host_id": host_id,
        "checklist_id": checklist_id,
        "review_count": len(reviews),
        "baseline_stig_id": baseline.get("stig_id"),
        "baseline_title": baseline.get("title"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SplunkRestError as err:
        print(f"Splunk REST error: {err}", file=sys.stderr)
        raise SystemExit(1) from err
