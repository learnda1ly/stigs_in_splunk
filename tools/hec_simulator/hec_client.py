"""POST stig:finding events to Splunk HEC (no splunk module required)."""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from typing import Any, Dict, List

APP_NAME = "stigs_in_splunk"
DEFAULT_HEC_URL = "https://localhost:8088/services/collector/event"
DEFAULT_INGEST_INDEX = "stig"
DEFAULT_INGEST_SOURCETYPE = "stig:finding"


def hec_settings_from_env() -> Dict[str, str]:
    return {
        "hec_url": (os.environ.get("SPLUNK_HEC_URL") or DEFAULT_HEC_URL).strip(),
        "hec_token": (os.environ.get("SPLUNK_HEC_TOKEN") or "").strip(),
        "ingest_index": (os.environ.get("SPLUNK_HEC_INDEX") or DEFAULT_INGEST_INDEX).strip(),
        "ingest_sourcetype": (
            os.environ.get("SPLUNK_HEC_SOURCETYPE") or DEFAULT_INGEST_SOURCETYPE
        ).strip(),
        "source": (os.environ.get("SPLUNK_HEC_SOURCE") or APP_NAME).strip(),
    }


def hec_payloads(
    events: List[Dict[str, Any]], index: str, sourcetype: str, source: str
) -> List[Dict[str, Any]]:
    """Same envelope as package/bin/services/hec.py _hec_payloads."""
    out: List[Dict[str, Any]] = []
    for event in events:
        item: Dict[str, Any] = {
            "event": event,
            "sourcetype": sourcetype,
            "index": index,
            "source": source or event.get("sourceRef") or APP_NAME,
        }
        if event.get("time"):
            item["time"] = event["time"]
        out.append(item)
    return out


def post_hec(
    url: str,
    token: str,
    events: List[Dict[str, Any]],
    *,
    index: str,
    sourcetype: str,
    source: str,
    verify_ssl: bool = False,
    timeout: int = 60,
) -> int:
    if not token:
        raise ValueError("SPLUNK_HEC_TOKEN is required to POST to HEC")
    if not events:
        return 0
    body = "\n".join(
        json.dumps(item, separators=(",", ":"))
        for item in hec_payloads(events, index, sourcetype, source)
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": "Splunk " + token,
            "Content-Type": "application/json",
        },
    )
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        resp.read()
        status = int(getattr(resp, "status", 200) or 200)
        if status >= 400:
            raise RuntimeError(f"HEC HTTP {status}")
    return len(events)
