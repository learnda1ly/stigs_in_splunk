"""Send stig:finding events to HEC. Token is read server-side only."""

from __future__ import annotations

import json
import os
import ssl
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

HEC_INPUT_NAME = "stig_findings"
HEC_STANZA = "http://stig_findings"
HEC_TOKEN_REALM = "stigs_in_splunk"
_HEC_CREDENTIAL_BY_INPUT = {
    "stig_findings": "hec_stig_findings",
    "stig_audit": "hec_stig_audit",
}


def emit_findings(
    events: List[Dict[str, Any]],
    settings: Optional[Dict[str, Any]] = None,
    session_key: str = "",
    source: str = APP_NAME,
) -> Dict[str, Any]:
    settings = settings or {}
    index = settings.get("ingest_index") or DEFAULT_INGEST_INDEX
    sourcetype = settings.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE
    url = (settings.get("hec_url") or DEFAULT_HEC_URL).strip()
    if not events:
        return {"indexed": 0, "via": "none"}
    token = lookup_hec_token(session_key)
    if token:
        try:
            sent = _post_hec(url, token, events, index, sourcetype, source)
            return {
                "indexed": sent,
                "via": "hec",
                "index": index,
                "sourcetype": sourcetype,
            }
        except Exception as exc:
            fallback = _post_receivers(events, index, sourcetype, source, session_key)
            fallback["hec_error"] = str(exc)
            return fallback
    return _post_receivers(events, index, sourcetype, source, session_key)


def lookup_hec_token(session_key: str = "") -> str:
    """Resolve the stig_findings HEC token without exposing it to the UI."""
    return lookup_hec_token_for_input(HEC_INPUT_NAME, HEC_STANZA, session_key)


def lookup_hec_token_for_input(
    input_name: str, stanza: str, session_key: str = ""
) -> str:
    token = _token_from_storage_passwords(input_name, session_key)
    if token:
        return token
    token = _token_from_rest(input_name, session_key)
    if token:
        return token
    return _token_from_local_inputs_conf(stanza)


def emit_indexed_events(
    events: List[Dict[str, Any]],
    *,
    index: str,
    sourcetype: str,
    session_key: str = "",
    hec_input_name: str = HEC_INPUT_NAME,
    hec_stanza: str = HEC_STANZA,
    source: str = APP_NAME,
) -> Dict[str, Any]:
    """Index JSON events via HEC (preferred) or receivers/simple."""
    if not events:
        return {"indexed": 0, "via": "none"}
    url = DEFAULT_HEC_URL
    token = lookup_hec_token_for_input(hec_input_name, hec_stanza, session_key)
    if token:
        try:
            sent = _post_hec(url, token, events, index, sourcetype, source)
            return {
                "indexed": sent,
                "via": "hec",
                "index": index,
                "sourcetype": sourcetype,
            }
        except Exception as exc:
            fallback = _post_receivers(events, index, sourcetype, source, session_key)
            fallback["hec_error"] = str(exc)
            return fallback
    return _post_receivers(events, index, sourcetype, source, session_key)


def _entry_token(data: Any) -> str:
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, dict) and content.get("token"):
            return str(content["token"]).strip()
        if data.get("token"):
            return str(data["token"]).strip()
        entries = data.get("entry") or []
        if entries:
            return _entry_token(entries[0])
    return ""


def _token_from_storage_passwords(input_name: str, session_key: str) -> str:
    """Read HEC token from encrypted storage/passwords (preferred on Cloud)."""
    if not _HAS_SPLUNK_REST or not session_key:
        return ""
    cred_name = _HEC_CREDENTIAL_BY_INPUT.get(input_name)
    if not cred_name:
        return ""
    path = (
        f"/servicesNS/nobody/{APP_NAME}/storage/passwords/"
        f"credential:{HEC_TOKEN_REALM}:{cred_name}:"
    )
    try:
        response, content = splunk.rest.simpleRequest(
            path,
            sessionKey=session_key,
            getargs={"output_mode": "json"},
            method="GET",
            raiseAllErrors=False,
        )
        status = int(response.get("status", 200))
        if status >= 400:
            return ""
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        data = json.loads(content) if isinstance(content, str) else content
        entries = data.get("entry") or []
        if not entries:
            return ""
        entry = entries[0]
        if isinstance(entry, dict):
            body = entry.get("content") or entry
            if isinstance(body, dict):
                clear = body.get("clear_password") or body.get("password")
                if clear:
                    return str(clear).strip()
    except Exception:
        return ""
    return ""


def _token_from_rest(input_name: str, session_key: str) -> str:
    if not _HAS_SPLUNK_REST or not session_key:
        return ""
    paths = (
        f"/servicesNS/nobody/{APP_NAME}/data/inputs/http/{input_name}",
        f"/services/data/inputs/http/{input_name}",
        "/servicesNS/nobody/splunk_httpinput/data/inputs/http/" + input_name,
    )
    for path in paths:
        try:
            response, content = splunk.rest.simpleRequest(
                path,
                sessionKey=session_key,
                getargs={"output_mode": "json"},
                method="GET",
                raiseAllErrors=False,
            )
            status = int(response.get("status", 200))
            if status >= 400:
                continue
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            data = json.loads(content) if isinstance(content, str) else content
            token = _entry_token(data)
            if token:
                return token
        except Exception:
            continue
    return ""


def _token_from_local_inputs_conf(stanza: str) -> str:
    """Fallback: read token from on-disk local inputs.conf only (never packaged default/)."""
    home = os.environ.get("SPLUNK_HOME") or ""
    if not home:
        return ""
    candidates = [
        os.path.join(home, "etc", "apps", APP_NAME, "local", "inputs.conf"),
        os.path.join(home, "etc", "apps", "splunk_httpinput", "local", "inputs.conf"),
        os.path.join(home, "etc", "system", "local", "inputs.conf"),
    ]
    for path in candidates:
        token = _parse_stanza_token(path, stanza)
        if token:
            return token
    return ""


def _parse_stanza_token(path: str, stanza: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return ""
    in_stanza = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_stanza = line[1:-1].strip() == stanza
            continue
        if in_stanza and "=" in line:
            key, val = line.split("=", 1)
            if key.strip() == "token":
                return val.strip().strip('"')
    return ""


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
    ctx = _hec_ssl_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        resp.read()
        status = int(getattr(resp, "status", 200) or 200)
        if status >= 400:
            raise RuntimeError(f"HEC HTTP {status}")
    return len(events)


def _hec_ssl_context() -> ssl.SSLContext:
    """Verify TLS by default; set STIG_HEC_TLS_VERIFY=0 only for local dev."""
    flag = os.environ.get("STIG_HEC_TLS_VERIFY", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return ssl._create_unverified_context()
    return ssl.create_default_context()


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
            "error": "HEC token unavailable and receivers/simple is unavailable",
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
