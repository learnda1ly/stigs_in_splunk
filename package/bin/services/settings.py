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


def _public(rec: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    token = rec.get("hec_token") or ""
    return {
        "_key": rec.get("_key") or "",
        "vim_mode": bool(as_bool(rec.get("vim_mode"))),
        "ingest_index": rec.get("ingest_index") or DEFAULT_INGEST_INDEX,
        "ingest_sourcetype": rec.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE,
        "hec_url": rec.get("hec_url") or DEFAULT_HEC_URL,
        "hec_token": token,
        "hec_token_set": bool(str(token).strip()),
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
    body = body or {}
    coll = kv_client.get_collection(service, KV_STIG_EDITOR_SETTINGS)
    rows = kv_client.query_all(coll)
    existing = dict(rows[0]) if rows else {}
    vim = as_bool(body["vim_mode"]) if "vim_mode" in body else as_bool(existing.get("vim_mode"))
    record = kv_record(
        {
            "vim_mode": bool(vim) if vim is not None else False,
            "ingest_index": _text(
                body.get("ingest_index"), existing.get("ingest_index") or DEFAULT_INGEST_INDEX
            )
            if "ingest_index" in body
            else (existing.get("ingest_index") or DEFAULT_INGEST_INDEX),
            "ingest_sourcetype": _text(
                body.get("ingest_sourcetype"),
                existing.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE,
            )
            if "ingest_sourcetype" in body
            else (existing.get("ingest_sourcetype") or DEFAULT_INGEST_SOURCETYPE),
            "hec_url": _text(body.get("hec_url"), existing.get("hec_url") or DEFAULT_HEC_URL)
            if "hec_url" in body
            else (existing.get("hec_url") or DEFAULT_HEC_URL),
            "hec_token": _text(body.get("hec_token"), existing.get("hec_token") or "")
            if "hec_token" in body
            else (existing.get("hec_token") or ""),
            "reconcile_earliest": _text(
                body.get("reconcile_earliest"),
                existing.get("reconcile_earliest") or DEFAULT_RECONCILE_EARLIEST,
            )
            if "reconcile_earliest" in body
            else (existing.get("reconcile_earliest") or DEFAULT_RECONCILE_EARLIEST),
            "updated_at": now_epoch(),
            "updated_by": username or "",
        }
    )
    if rows and rows[0].get("_key"):
        stored = kv_client.update_record(coll, rows[0]["_key"], record)
    else:
        stored = kv_client.insert_record(coll, record)
    return _public(stored, username)
