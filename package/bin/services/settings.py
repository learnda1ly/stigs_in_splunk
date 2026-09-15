"""App-wide STIG editor and ingest settings (KV, not conf files)."""

from __future__ import annotations

from typing import Any, Dict

import kv_client
from models import (
    DEFAULT_HEC_URL,
    DEFAULT_INGEST_INDEX,
    DEFAULT_INGEST_SOURCETYPE,
    DEFAULT_RECONCILE_EARLIEST,
    KV_STIG_EDITOR_SETTINGS,
    as_bool,
    kv_record,
    now_epoch,
)


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
        "_key": rec.get("_key") or "",
        "vim_mode": bool(as_bool(rec.get("vim_mode"))),
        "ingest_index": rec.get("ingest_index") or DEFAULT_INGEST_INDEX,
        "ingest_sourcetype": rec.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE,
        "hec_url": rec.get("hec_url") or DEFAULT_HEC_URL,
        "reconcile_earliest": rec.get("reconcile_earliest") or DEFAULT_RECONCILE_EARLIEST,
        "updated_at": rec.get("updated_at") or 0,
        "updated_by": rec.get("updated_by") or username or "",
    }


def get_settings(service) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    rows = kv_client.query_all(coll)
    rec = rows[0] if rows else {}
    return _public(rec)


def save_settings(service, body: Dict[str, Any], username: str) -> Dict[str, Any]:
    body = dict(body or {})
    body.pop("hec_token", None)
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    rows = kv_client.query_all(coll)
    existing = dict(rows[0]) if rows else {}
    vim = as_bool(body["vim_mode"]) if "vim_mode" in body else as_bool(existing.get("vim_mode"))
    record = kv_record(
        {
            "vim_mode": bool(vim) if vim is not None else False,
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
    )
    if rows and rows[0].get("_key"):
        stored = kv_client.update_record(coll, rows[0]["_key"], record)
    else:
        stored = kv_client.insert_record(coll, record)
    return _public(stored, username)
