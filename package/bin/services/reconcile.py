"""Read stig:finding events from the index and apply them to KV."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from models import DEFAULT_INGEST_INDEX, DEFAULT_INGEST_SOURCETYPE, DEFAULT_RECONCILE_EARLIEST
from services import apply as apply_svc
from services import settings as settings_svc

try:
    import splunk.rest  # type: ignore

    _HAS_SPLUNK_REST = True
except ImportError:
    _HAS_SPLUNK_REST = False


def _json_load(raw: Any) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        return json.loads(raw)
    return raw


def _search_events(
    session_key: str,
    index: str,
    sourcetype: str,
    earliest: str,
    latest: str = "now",
) -> List[Dict[str, Any]]:
    if not _HAS_SPLUNK_REST:
        raise RuntimeError("index search is only available inside Splunk")
    query = (
        f'search index={index} sourcetype="{sourcetype}" '
        f"earliest={earliest} latest={latest} | sort 0 _time"
    )
    response, content = splunk.rest.simpleRequest(
        "/services/search/jobs",
        sessionKey=session_key,
        postargs={"search": query, "output_mode": "json", "exec_mode": "oneshot", "count": "0"},
        method="POST",
        raiseAllErrors=False,
    )
    status = int(response.get("status", 200))
    if status >= 400:
        raise RuntimeError(f"search failed ({status}): {str(content)[:300]}")
    parsed = _json_load(content)
    events: List[Dict[str, Any]] = []
    rows = []
    if isinstance(parsed, dict):
        rows = parsed.get("results") or parsed.get("entry") or []
        if isinstance(parsed.get("results"), dict):
            rows = parsed["results"].get("results") or []
    if not rows and isinstance(content, (str, bytes)):
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        if "<results" in text:
            root = ET.fromstring(text)
            for result in root.findall(".//{*}result"):
                fields = {}
                for field in result.findall("{*}field"):
                    name = field.get("k") or field.get("name")
                    value_el = field.find("{*}value/{*}text")
                    if name:
                        fields[name] = (value_el.text if value_el is not None else "") or ""
                rows.append(fields)
    for row in rows:
        raw = row.get("_raw") or row.get("raw") or row
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except ValueError:
                continue
        elif isinstance(raw, dict):
            payload = raw
        else:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("event"), dict):
            inner = dict(payload["event"])
            inner.setdefault("time", payload.get("time") or row.get("_time"))
            payload = inner
        if isinstance(payload, dict):
            events.append(payload)
    return events


def reconcile_from_index(
    service,
    session: Dict[str, Any],
    username: str,
    earliest: Optional[str] = None,
) -> Dict[str, Any]:
    settings = settings_svc.get_settings(service)
    index = settings.get("ingest_index") or DEFAULT_INGEST_INDEX
    sourcetype = settings.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE
    window = earliest or settings.get("reconcile_earliest") or DEFAULT_RECONCILE_EARLIEST
    session_key = (session or {}).get("authtoken") or ""
    started = time.time()
    events = _search_events(session_key, index, sourcetype, window)
    applied = apply_svc.apply_finding_events(service, events, username, session)
    applied.update(
        {
            "index": index,
            "sourcetype": sourcetype,
            "earliest": window,
            "scanned": len(events),
            "elapsed_sec": round(time.time() - started, 3),
        }
    )
    return applied
