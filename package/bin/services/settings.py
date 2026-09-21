"""Editor and ingest settings stored in the UCC Configuration conf file.

The Configuration page writes ``stigs_in_splunk_settings.conf`` stanza
``[general]``. ``/stig_settings`` remains a JSON adapter for the editor vim
toggle. The HEC token is never stored here.
"""

from __future__ import annotations

from typing import Any, Dict

import kv_client
from models import (
    APP_NAME,
    DEFAULT_HEC_URL,
    DEFAULT_INGEST_INDEX,
    DEFAULT_INGEST_SOURCETYPE,
    DEFAULT_RECONCILE_EARLIEST,
    KV_STIG_EDITOR_SETTINGS,
    as_bool,
    kv_record,
    now_epoch,
)

UCC_SETTINGS_CONF = "stigs_in_splunk_settings"
UCC_SETTINGS_STANZA = "general"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _pick(body: Dict[str, Any], existing: Dict[str, Any], key: str, default: str) -> str:
    if key in body:
        return _text(body.get(key), default)
    return existing.get(key) or default


def _public(rec: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    return {
        "_key": rec.get("_key") or UCC_SETTINGS_STANZA,
        "vim_mode": bool(as_bool(rec.get("vim_mode"))),
        "trust_event_collection_id": bool(as_bool(rec.get("trust_event_collection_id"))),
        "ingest_index": rec.get("ingest_index") or DEFAULT_INGEST_INDEX,
        "ingest_sourcetype": rec.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE,
        "hec_url": rec.get("hec_url") or DEFAULT_HEC_URL,
        "reconcile_earliest": rec.get("reconcile_earliest") or DEFAULT_RECONCILE_EARLIEST,
        "updated_at": rec.get("updated_at") or 0,
        "updated_by": rec.get("updated_by") or username or "",
    }


def _session_key(service) -> str:
    return str(getattr(service, "_session_key", "") or "")


def _eai_content(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    entries = data.get("entry") or []
    if entries:
        content = entries[0].get("content")
        if isinstance(content, dict):
            return content
        return {}
    return data


def _read_ucc(session_key: str) -> Dict[str, Any]:
    if not session_key:
        return {}
    try:
        import splunk.rest  # type: ignore
    except ImportError:
        return {}
    path = (
        f"/servicesNS/nobody/{APP_NAME}/configs/conf-{UCC_SETTINGS_CONF}/"
        + UCC_SETTINGS_STANZA
    )
    try:
        response, content = splunk.rest.simpleRequest(
            path,
            sessionKey=session_key,
            getargs={"output_mode": "json"},
            method="GET",
            raiseAllErrors=False,
        )
    except Exception:
        return {}
    status = int(response.get("status", 200))
    if status >= 400:
        return {}
    parsed = kv_client._parse_content(content)
    rec = _eai_content(parsed)
    rec.pop("disabled", None)
    rec.pop("eai:acl", None)
    rec.pop("eai:appName", None)
    rec.pop("eai:userName", None)
    rec.pop("eai:attributes", None)
    return rec


def _write_ucc(session_key: str, record: Dict[str, Any]) -> bool:
    if not session_key:
        return False
    try:
        import splunk.rest  # type: ignore
    except ImportError:
        return False
    postargs = {
        "vim_mode": "1" if as_bool(record.get("vim_mode")) else "0",
        "trust_event_collection_id": (
            "1" if as_bool(record.get("trust_event_collection_id")) else "0"
        ),
        "ingest_index": record.get("ingest_index") or DEFAULT_INGEST_INDEX,
        "ingest_sourcetype": record.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE,
        "hec_url": record.get("hec_url") or DEFAULT_HEC_URL,
        "reconcile_earliest": record.get("reconcile_earliest") or DEFAULT_RECONCILE_EARLIEST,
    }
    existing = _read_ucc(session_key)
    if existing:
        path = (
            f"/servicesNS/nobody/{APP_NAME}/configs/conf-{UCC_SETTINGS_CONF}/"
            + UCC_SETTINGS_STANZA
        )
        extra: Dict[str, str] = {}
    else:
        path = f"/servicesNS/nobody/{APP_NAME}/configs/conf-{UCC_SETTINGS_CONF}"
        extra = {"name": UCC_SETTINGS_STANZA}
    try:
        response, _content = splunk.rest.simpleRequest(
            path,
            sessionKey=session_key,
            getargs={"output_mode": "json"},
            postargs={**extra, **postargs},
            method="POST",
            raiseAllErrors=False,
        )
    except Exception:
        return False
    return int(response.get("status", 200)) < 400


def _read_kv(service) -> Dict[str, Any]:
    try:
        coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
        rows = kv_client.query_all(coll)
    except Exception:
        return {}
    return dict(rows[0]) if rows else {}


def get_settings(service) -> Dict[str, Any]:
    rec = _read_ucc(_session_key(service))
    if not rec:
        rec = _read_kv(service)
    return _public(rec)


def save_settings(service, body: Dict[str, Any], username: str) -> Dict[str, Any]:
    body = dict(body or {})
    body.pop("hec_token", None)
    existing = _read_ucc(_session_key(service)) or _read_kv(service)
    vim = as_bool(body["vim_mode"]) if "vim_mode" in body else as_bool(existing.get("vim_mode"))
    trust = (
        as_bool(body["trust_event_collection_id"])
        if "trust_event_collection_id" in body
        else as_bool(existing.get("trust_event_collection_id"))
    )
    record = {
        "vim_mode": bool(vim) if vim is not None else False,
        "trust_event_collection_id": bool(trust) if trust is not None else False,
        "ingest_index": _pick(body, existing, "ingest_index", DEFAULT_INGEST_INDEX),
        "ingest_sourcetype": _pick(
            body, existing, "ingest_sourcetype", DEFAULT_INGEST_SOURCETYPE
        ),
        "hec_url": _pick(body, existing, "hec_url", DEFAULT_HEC_URL),
        "reconcile_earliest": _pick(
            body, existing, "reconcile_earliest", DEFAULT_RECONCILE_EARLIEST
        ),
        "updated_at": now_epoch(),
        "updated_by": username or "",
    }
    if _write_ucc(_session_key(service), record):
        return _public(record, username)
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    rows = kv_client.query_all(coll)
    stored_body = kv_record(record)
    if rows and rows[0].get("_key"):
        stored = kv_client.update_record(coll, rows[0]["_key"], stored_body)
    else:
        stored = kv_client.insert_record(coll, stored_body)
    return _public(stored, username)
