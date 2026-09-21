"""Workspace assignment rules and host×baseline overrides (Option A resolver)."""

from __future__ import annotations

import fnmatch
import ipaddress
import re
from typing import Any, Dict, List, Optional, Tuple

import audit
import kv_client
from models import (
    KV_STIG_ASSIGNMENT_RULES,
    KV_STIG_HOST_BASELINE_ASSIGNMENTS,
    as_bool,
    dumps_json,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)
from services import collections as collections_svc
from services import settings as settings_svc

REASON_OVERRIDE = "override"
REASON_RULE = "rule"
REASON_EVENT_COLLECTION = "event_collection_id"
REASON_DEFAULT = "default"
REASON_FORCED = "forced_import"


def _hostname(event: Dict[str, Any]) -> str:
    asset = event.get("asset") or {}
    return (event.get("assetName") or asset.get("name") or "").strip()


def _benchmark_id(event: Dict[str, Any]) -> str:
    stig = event.get("stig") or {}
    return (event.get("benchmarkId") or stig.get("stig_id") or "").strip()


def _event_ip(event: Dict[str, Any]) -> str:
    asset = event.get("asset") or {}
    return (asset.get("ip") or "").strip()


def _package_id(event: Dict[str, Any]) -> str:
    return str(event.get("package_id") or "").strip()


def _normalize_hostname_key(hostname: str) -> str:
    return (hostname or "").strip().casefold()


def list_rules(service) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    rows = kv_client.query_all(coll)
    rows.sort(key=lambda rec: (float(rec.get("priority") or 0), rec.get("_key") or ""))
    return rows


def get_rule(service, key: str) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    return kv_client.get_by_key(coll, key)


def create_rule(service, body: Dict[str, Any], username: str) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    key = new_id()
    ts = now_epoch()
    match = body.get("match_json")
    if isinstance(match, dict):
        match = dumps_json(match)
    record = kv_record(
        {
            "_key": key,
            "priority": float(body.get("priority") if body.get("priority") is not None else 100),
            "enabled": bool(as_bool(body.get("enabled", True))),
            "name": (body.get("name") or "Untitled rule").strip() or "Untitled rule",
            "target_stig_collection_id": (body.get("target_stig_collection_id") or "").strip(),
            "match_json": match if isinstance(match, str) else dumps_json(match or {}),
            "stop_on_match": bool(as_bool(body.get("stop_on_match", True))),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    if not record.get("target_stig_collection_id"):
        raise ValueError("target_stig_collection_id is required")
    stored = kv_client.insert_record(coll, record)
    audit.log_event(
        "assignment_rule.create",
        "stig_assignment_rule",
        key,
        username,
        {"name": stored.get("name"), "priority": stored.get("priority")},
    )
    return stored


def update_rule(service, key: str, body: Dict[str, Any], username: str) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    patch = dict(existing)
    for field in (
        "priority",
        "enabled",
        "name",
        "target_stig_collection_id",
        "stop_on_match",
    ):
        if field in body:
            if field == "priority":
                patch[field] = float(body[field])
            elif field in ("enabled", "stop_on_match"):
                patch[field] = bool(as_bool(body[field]))
            else:
                patch[field] = body[field]
    if "match_json" in body:
        match = body["match_json"]
        if isinstance(match, dict):
            match = dumps_json(match)
        patch["match_json"] = match
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("assignment_rule.update", "stig_assignment_rule", key, username, body)
    return stored


def delete_rule(service, key: str, username: str) -> None:
    coll = kv_client.get_collection(service, KV_STIG_ASSIGNMENT_RULES)
    if not kv_client.get_by_key(coll, key):
        raise KeyError(key)
    kv_client.delete_record(coll, key)
    audit.log_event("assignment_rule.delete", "stig_assignment_rule", key, username)


def list_overrides(service) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    return kv_client.query_all(coll)


def get_override(service, key: str) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    return kv_client.get_by_key(coll, key)


def create_override(service, body: Dict[str, Any], username: str) -> Dict[str, Any]:
    hostname = _normalize_hostname_key(body.get("hostname") or "")
    benchmark_id = (body.get("benchmark_id") or "").strip()
    target = (body.get("target_stig_collection_id") or "").strip()
    if not hostname or not benchmark_id or not target:
        raise ValueError("hostname, benchmark_id, and target_stig_collection_id are required")
    coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    key = new_id()
    ts = now_epoch()
    record = kv_record(
        {
            "_key": key,
            "hostname": hostname,
            "benchmark_id": benchmark_id,
            "target_stig_collection_id": target,
            "note": body.get("note") or "",
            "expires_at": float(body.get("expires_at") or 0),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored = kv_client.insert_record(coll, record)
    audit.log_event(
        "override.create",
        "stig_host_baseline_assignment",
        key,
        username,
        {"hostname": hostname, "benchmark_id": benchmark_id},
    )
    return stored


def update_override(service, key: str, body: Dict[str, Any], username: str) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    patch = dict(existing)
    if "hostname" in body:
        patch["hostname"] = _normalize_hostname_key(body.get("hostname") or "")
    for field in ("benchmark_id", "target_stig_collection_id", "note"):
        if field in body:
            patch[field] = body[field]
    if "expires_at" in body:
        patch["expires_at"] = float(body.get("expires_at") or 0)
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("override.update", "stig_host_baseline_assignment", key, username, body)
    return stored


def delete_override(service, key: str, username: str) -> None:
    coll = kv_client.get_collection(service, KV_STIG_HOST_BASELINE_ASSIGNMENTS)
    if not kv_client.get_by_key(coll, key):
        raise KeyError(key)
    kv_client.delete_record(coll, key)
    audit.log_event("override.delete", "stig_host_baseline_assignment", key, username)


def _match_hostname(pattern: str, hostname: str, mode: str) -> bool:
    if not pattern:
        return True
    host = hostname or ""
    mode = (mode or "glob").strip().lower()
    if mode == "regex":
        try:
            return bool(re.search(pattern, host, re.IGNORECASE))
        except re.error:
            return False
    if mode == "exact":
        return host.casefold() == pattern.strip().casefold()
    if mode == "suffix":
        return host.casefold().endswith(pattern.strip().casefold())
    return fnmatch.fnmatchcase(host.casefold(), pattern.strip().casefold())


def _match_cidr(cidr: str, ip: str) -> bool:
    if not cidr:
        return True
    if not ip:
        return False
    try:
        network = ipaddress.ip_network(cidr.strip(), strict=False)
        return ipaddress.ip_address(ip.strip()) in network
    except ValueError:
        return False


def _match_scalar(pattern: Any, value: str) -> bool:
    if pattern is None or pattern == "":
        return True
    if isinstance(pattern, list):
        want = (value or "").strip().casefold()
        return any(str(item).strip().casefold() == want for item in pattern)
    return str(pattern).strip().casefold() == (value or "").strip().casefold()


def rule_matches(event: Dict[str, Any], match: Dict[str, Any]) -> bool:
    if not match:
        return False
    hostname = _hostname(event)
    if not _match_hostname(
        match.get("hostname") or "",
        hostname,
        match.get("hostname_mode") or "glob",
    ):
        return False
    if not _match_scalar(match.get("benchmark_id"), _benchmark_id(event)):
        return False
    if not _match_scalar(match.get("package_id"), _package_id(event)):
        return False
    if not _match_scalar(match.get("source_product"), str(event.get("source_product") or "")):
        return False
    if not _match_scalar(
        match.get("collection_name") or match.get("collectionName"),
        str(event.get("collectionName") or ""),
    ):
        return False
    if not _match_cidr(match.get("ip_cidr") or "", _event_ip(event)):
        return False
    return True


def _find_override(
    service, event: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    hostname_key = _normalize_hostname_key(_hostname(event))
    benchmark = _benchmark_id(event)
    if not hostname_key or not benchmark:
        return None
    now = now_epoch()
    for row in list_overrides(service):
        if _normalize_hostname_key(row.get("hostname") or "") != hostname_key:
            continue
        if (row.get("benchmark_id") or "").strip() != benchmark:
            continue
        expires = float(row.get("expires_at") or 0)
        if expires and expires < now:
            continue
        return row
    return None


def _find_rule_match(service, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for rule in list_rules(service):
        if not as_bool(rule.get("enabled", True)):
            continue
        match = parse_json_field(rule.get("match_json"), default={}) or {}
        if not isinstance(match, dict):
            continue
        if rule_matches(event, match):
            return rule
    return None


def resolve_collection_id(
    event: Dict[str, Any],
    service,
    session: Dict[str, Any],
    *,
    forced_collection_id: str = "",
    username: str = "system",
    audit_resolve: bool = True,
) -> Dict[str, Any]:
    """Return stig_collection_id plus reason metadata for one normalized event."""
    if forced_collection_id:
        out = {
            "stig_collection_id": forced_collection_id,
            "reason": REASON_FORCED,
            "rule_key": None,
            "override_key": None,
        }
        if audit_resolve:
            audit.log_event(
                "workspace_resolve",
                "stig_finding",
                _hostname(event) or "unknown",
                username,
                {
                    "reason": REASON_FORCED,
                    "benchmark_id": _benchmark_id(event),
                    "target": forced_collection_id,
                },
            )
        return out

    override = _find_override(service, event)
    if override:
        target = override.get("target_stig_collection_id") or ""
        out = {
            "stig_collection_id": target,
            "reason": REASON_OVERRIDE,
            "rule_key": None,
            "override_key": override.get("_key"),
        }
        if audit_resolve:
            audit.log_event(
                "workspace_resolve",
                "stig_finding",
                _hostname(event) or "unknown",
                username,
                {
                    "reason": REASON_OVERRIDE,
                    "benchmark_id": _benchmark_id(event),
                    "target": target,
                    "override_key": override.get("_key"),
                },
            )
        return out

    rule = _find_rule_match(service, event)
    if rule:
        target = rule.get("target_stig_collection_id") or ""
        out = {
            "stig_collection_id": target,
            "reason": REASON_RULE,
            "rule_key": rule.get("_key"),
            "override_key": None,
        }
        if audit_resolve:
            audit.log_event(
                "workspace_resolve",
                "stig_finding",
                _hostname(event) or "unknown",
                username,
                {
                    "reason": REASON_RULE,
                    "benchmark_id": _benchmark_id(event),
                    "target": target,
                    "rule_id": rule.get("_key"),
                    "rule_name": rule.get("name"),
                },
            )
        return out

    settings = settings_svc.get_settings(service)
    trust = bool(as_bool(settings.get("trust_event_collection_id")))
    event_cid = (event.get("collectionId") or "").strip()
    if trust and event_cid:
        out = {
            "stig_collection_id": event_cid,
            "reason": REASON_EVENT_COLLECTION,
            "rule_key": None,
            "override_key": None,
        }
        if audit_resolve:
            audit.log_event(
                "workspace_resolve",
                "stig_finding",
                _hostname(event) or "unknown",
                username,
                {
                    "reason": REASON_EVENT_COLLECTION,
                    "benchmark_id": _benchmark_id(event),
                    "target": event_cid,
                },
            )
        return out

    default_rec = collections_svc.ensure_default_collection(
        service, (session or {}).get("user") or username
    )
    target = default_rec["_key"]
    out = {
        "stig_collection_id": target,
        "reason": REASON_DEFAULT,
        "rule_key": None,
        "override_key": None,
    }
    if audit_resolve:
        audit.log_event(
            "workspace_resolve",
            "stig_finding",
            _hostname(event) or "unknown",
            username,
            {
                "reason": REASON_DEFAULT,
                "benchmark_id": _benchmark_id(event),
                "target": target,
            },
        )
    return out


def preview_resolution(
    service,
    event: Dict[str, Any],
    session: Dict[str, Any],
    username: str = "system",
) -> Dict[str, Any]:
    return resolve_collection_id(
        event, service, session, username=username, audit_resolve=False
    )
