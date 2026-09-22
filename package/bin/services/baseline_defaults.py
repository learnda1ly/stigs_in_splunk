"""Per-workspace default baseline (STIG revision) resolution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import audit
import kv_client
from models import (
    KV_STIG_COLLECTIONS,
    dumps_json,
    kv_record,
    now_epoch,
    parse_json_field,
)
from services import baselines as baselines_svc
from services import collections as collections_svc

DEFAULTS_FIELD = "default_baseline_map"


def _normalize_stig_key(stig_id: str) -> str:
    return (stig_id or "").strip().casefold()


def _default_baseline_allowed(
    baseline: Dict[str, Any], collection_id: str
) -> bool:
    scope = baselines_svc.baseline_workspace_id(baseline)
    if not scope:
        return True
    return scope == (collection_id or "").strip()


def _parse_map(rec: Optional[Dict[str, Any]]) -> Dict[str, str]:
    raw = parse_json_field((rec or {}).get(DEFAULTS_FIELD), default={}) or {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key, val in raw.items():
        nk = _normalize_stig_key(str(key))
        bid = str(val or "").strip()
        if nk and bid:
            out[nk] = bid
    return out


def _require_write(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    from services import grants as grants_svc

    rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not ctx.can_write:
        raise PermissionError("access denied to stig_collection")
    return rec


def _require_read(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    from services import grants as grants_svc

    rec, ctx, _grants = grants_svc.workspace_context(service, collection_id, session)
    if not ctx.can_read:
        raise KeyError(collection_id)
    return rec


def _persist_map(
    service, collection_id: str, mapping: Dict[str, str], username: str
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_COLLECTIONS)
    existing = kv_client.get_by_key(coll, collection_id)
    if not existing:
        raise KeyError(collection_id)
    patch = dict(existing)
    patch[DEFAULTS_FIELD] = dumps_json(mapping)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    return kv_client.update_record(coll, collection_id, kv_record(patch))


def list_defaults(
    service, collection_id: str, session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    rec = _require_read(service, collection_id, session)
    mapping = _parse_map(rec)
    rows: List[Dict[str, Any]] = []
    for stig_key, baseline_id in sorted(mapping.items()):
        baseline = baselines_svc.get_baseline(service, baseline_id)
        rows.append(
            {
                "stig_id": stig_key,
                "baseline_id": baseline_id,
                "baseline_title": (baseline or {}).get("title") or "",
                "baseline_version": (baseline or {}).get("version") or "",
                "xccdf_benchmark_id": (baseline or {}).get("xccdf_benchmark_id") or "",
                "missing_baseline": baseline is None,
            }
        )
    return rows


def set_default(
    service,
    collection_id: str,
    stig_id: str,
    baseline_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    stig_key = _normalize_stig_key(stig_id)
    bid = (baseline_id or "").strip()
    if not stig_key or not bid:
        raise ValueError("stig_id and baseline_id are required")
    baseline = baselines_svc.require_baseline_usable_in_workspace(
        service, session, bid, collection_id
    )
    bench_stig = _normalize_stig_key(baseline.get("stig_id") or "")
    bench_xccdf = _normalize_stig_key(baseline.get("xccdf_benchmark_id") or "")
    allowed = {bench_stig, bench_xccdf}
    if bench_xccdf and "_benchmark_" in (baseline.get("xccdf_benchmark_id") or ""):
        allowed.add(_normalize_stig_key((baseline.get("xccdf_benchmark_id") or "").split("_benchmark_")[-1]))
    if bench_stig and stig_key not in allowed:
        raise ValueError(
            "stig_id must match the baseline stig_id or xccdf_benchmark_id"
        )
    rec = collections_svc.get_collection(service, collection_id)
    mapping = _parse_map(rec)
    mapping[stig_key] = bid
    stored = _persist_map(service, collection_id, mapping, username)
    audit.log_event(
        "update",
        "stig_collection_baseline_default",
        collection_id,
        username,
        {"stig_id": stig_id, "baseline_id": bid},
    )
    return {
        "stig_collection_id": collection_id,
        "stig_id": stig_id,
        "baseline_id": bid,
        "collection": stored,
    }


def delete_default(
    service,
    collection_id: str,
    stig_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    stig_key = _normalize_stig_key(stig_id)
    if not stig_key:
        raise ValueError("stig_id is required")
    rec = collections_svc.get_collection(service, collection_id)
    mapping = _parse_map(rec)
    if stig_key not in mapping:
        raise KeyError(stig_id)
    del mapping[stig_key]
    _persist_map(service, collection_id, mapping, username)
    audit.log_event(
        "delete",
        "stig_collection_baseline_default",
        collection_id,
        username,
        {"stig_id": stig_id},
    )
    return {"deleted": stig_id, "stig_collection_id": collection_id}


def lookup_default_baseline_id(
    service, collection_id: str, stig_id: str, xccdf_benchmark_id: str = ""
) -> Optional[str]:
    if not collection_id:
        return None
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        return None
    mapping = _parse_map(rec)
    for candidate in (stig_id, xccdf_benchmark_id):
        key = _normalize_stig_key(candidate)
        if key and key in mapping:
            bid = mapping[key]
            baseline = baselines_svc.get_baseline(service, bid)
            if baseline and _default_baseline_allowed(baseline, collection_id):
                return bid
    return None


def resolve_baseline_id(
    service,
    *,
    collection_id: str = "",
    explicit_baseline_id: str = "",
    stig_id: str = "",
    xccdf_benchmark_id: str = "",
    version: str = "",
) -> Optional[str]:
    """Precedence: explicit baseline_id, workspace default, versioned catalog match, latest catalog."""
    explicit = (explicit_baseline_id or "").strip()
    if explicit:
        if baselines_svc.get_baseline(service, explicit):
            return explicit
        raise KeyError(explicit)

    if collection_id:
        default_bid = lookup_default_baseline_id(
            service, collection_id, stig_id, xccdf_benchmark_id
        )
        if default_bid:
            return default_bid

    want_stig = (stig_id or "").strip()
    if not want_stig and xccdf_benchmark_id:
        if "_benchmark_" in xccdf_benchmark_id:
            want_stig = xccdf_benchmark_id.split("_benchmark_")[-1]
        else:
            want_stig = xccdf_benchmark_id
    if want_stig:
        cid = (collection_id or "").strip()
        if cid:
            found = baselines_svc.find_baseline_by_stig(
                service, want_stig, version or "", stig_collection_id=cid
            )
            if found:
                return found["_key"]
        found = baselines_svc.find_baseline_by_stig(service, want_stig, version or "")
        if found:
            return found["_key"]
    return None
