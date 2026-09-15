"""Send stig:finding events to HEC, with receivers/simple as in-app fallback."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from models import (
    APP_NAME,
    DEFAULT_HEC_URL,
    DEFAULT_INGEST_INDEX,
    DEFAULT_INGEST_SOURCETYPE,
)

try:
    import splunk.rest  # type: ignore

    _HAS_SPLUNK_REST = True
except ImportError:
    _HAS_SPLUNK_REST = False


def emit_findings(
    events: List[Dict[str, Any]],
    settings: Optional[Dict[str, Any]] = None,
    session_key: str = "",
    source: str = APP_NAME,
) -> Dict[str, Any]:
    settings = settings or {}
    index = settings.get("ingest_index") or DEFAULT_INGEST_INDEX
    sourcetype = settings.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE
    token = (settings.get("hec_token") or "").strip()
    url = (settings.get("hec_url") or DEFAULT_HEC_URL).strip()
    if not events:
        return {"indexed": 0, "via": "none"}
    if token:
        try:
            sent = _post_hec(url, token, events, index, sourcetype, source)
            return {"indexed": sent, "via": "hec", "index": index, "sourcetype": sourcetype}
        except Exception as exc:
            fallback = _post_receivers(events, index, sourcetype, source, session_key)
            fallback["hec_error"] = str(exc)
            return fallback
    return _post_receivers(events, index, sourcetype, source, session_key)


def _hec_payloads(
    events: List[Dict[str, Any]], index: str, sourcetype: str, source: str
) -> List[Dict[str, Any]]:
    out = []
    for event in events:
        item = {
            "event": event,
            "sourcetype": sourcetype,
            "index": index,
            "source": source or event.get("sourceRef") or APP_NAME,
        }
        if event.get("time"):
            item["time"] = event["time"]
        out.append(item)
    return out


def _post_hec(
    url: str,
    token: str,
    events: List[Dict[str, Any]],
    index: str,
    sourcetype: str,
    source: str,
) -> int:
    body = "\n".join(
        json.dumps(item, separators=(",", ":"))
        for item in _hec_payloads(events, index, sourcetype, source)
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
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        resp.read()
        status = int(getattr(resp, "status", 200) or 200)
        if status >= 400:
            raise RuntimeError(f"HEC HTTP {status}")
    return len(events)


def _post_receivers(
    events: List[Dict[str, Any]],
    index: str,
    sourcetype: str,
    source: str,
    session_key: str,
) -> Dict[str, Any]:
    if not _HAS_SPLUNK_REST or not session_key:
        return {
            "indexed": 0,
            "via": "none",
            "index": index,
            "sourcetype": sourcetype,
            "error": "HEC token not configured and receivers/simple is unavailable",
        }
    sent = 0
    last_error = ""
    path = "/services/receivers/simple"
    for event in events:
        try:
            getargs = {
                "index": index,
                "sourcetype": sourcetype,
                "source": source or event.get("sourceRef") or APP_NAME,
                "output_mode": "json",
            }
            response, _content = splunk.rest.simpleRequest(
                path,
                sessionKey=session_key,
                getargs=getargs,
                method="POST",
                jsonargs=json.dumps(event),
                raiseAllErrors=False,
            )
            status = int(response.get("status", 200))
            if status >= 400:
                last_error = f"receivers/simple HTTP {status}"
                continue
            sent += 1
        except Exception as exc:
            last_error = str(exc)
    out = {
        "indexed": sent,
        "via": "receivers",
        "index": index,
        "sourcetype": sourcetype,
    }
    if last_error and sent < len(events):
        out["error"] = last_error
    return out
