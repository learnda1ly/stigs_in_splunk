"""Apply streamed stig:finding events to KV current state.

Incoming findings are authoritative unless the existing review has ingest_lock.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import audit
from importers.events import finding_key, normalize_finding_event
from importers.ingest import reviews_to_seeds
from models import parse_json_field
from services import baselines as baselines_svc
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import hosts as hosts_svc


def _upsert_host(
    service,
    event: Dict[str, Any],
    collection_id: str,
    username: str,
    session: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    asset = event.get("asset") or {}
    hostname = event.get("assetName") or asset.get("name") or ""
    existing = hosts_svc.find_host_by_hostname(
        service, session, collection_id, hostname
    )
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    body = {
        "stig_collection_id": collection_id,
        "hostname": hostname,
        "ip_address": asset.get("ip") or "",
        "fqdn": asset.get("fqdn") or "",
        "mac_address": asset.get("mac") or "",
        "role": metadata.get("cklRole") or "None",
        "asset_type": "Non-Computing" if asset.get("noncomputing") else "Computing",
        "tech_area": metadata.get("cklTechArea") or "",
        "web_or_database": metadata.get("cklWebOrDatabase") == "true",
        "metadata": metadata,
    }
    if not existing:
        return hosts_svc.create_host(service, body, username, session), True
    patch = {}
    for src, dest in (("ip", "ip_address"), ("fqdn", "fqdn"), ("mac", "mac_address")):
        val = asset.get(src)
        if val and val != existing.get(dest):
            patch[dest] = val
    if metadata.get("cklRole") and metadata["cklRole"] != existing.get("role"):
        patch["role"] = metadata["cklRole"]
    if patch:
        existing = hosts_svc.update_host(
            service, existing["_key"], patch, username, session
        )
    return existing, False


def _upsert_baseline(
    service,
    events: List[Dict[str, Any]],
    username: str,
) -> Tuple[Dict[str, Any], bool]:
    first = events[0]
    meta = dict(first.get("stig") or {})
    if not meta.get("stig_id"):
        meta["stig_id"] = first.get("benchmarkId") or ""
    meta.setdefault("source_type", first.get("source_product") or "hec")
    rules = []
    seen = set()
    for event in events:
        rule = dict(event.get("rule") or {})
        key = rule.get("rule_id_src") or rule.get("rule_id") or rule.get("group_id") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        rules.append(rule)
    if not rules:
        existing = baselines_svc.find_baseline_by_stig(
            service, meta.get("stig_id") or "", meta.get("version") or ""
        )
        if not existing:
            raise ValueError(
                f"no baseline for {meta.get('stig_id')} and event has no rule body"
            )
        return existing, False
    return baselines_svc.import_parsed_baseline(
        service,
        meta,
        rules,
        username,
        source_uri=first.get("sourceRef") or "",
        format_name=meta.get("source_type") or "hec",
        match_stig_id=True,
    )


def apply_finding_events(
    service,
    events: List[Dict[str, Any]],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = []
    errors: List[str] = []
    for raw in events or []:
        try:
            normalized.append(normalize_finding_event(raw))
        except ValueError as exc:
            errors.append(str(exc))

    groups: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for event in normalized:
        gkey = "|".join(
            [
                event.get("collectionId") or "",
                (event.get("assetName") or "").casefold(),
                (event.get("benchmarkId") or "").casefold(),
            ]
        )
        groups.setdefault(gkey, {})
        groups[gkey][finding_key(event)] = event

    host_created = 0
    checklist_created = 0
    applied = 0
    locked = 0
    unmatched = 0
    checklists: List[Dict[str, Any]] = []

    for batch_map in groups.values():
        batch = list(batch_map.values())
        first = batch[0]
        collection_id = first.get("collectionId") or ""
        if not collection_id:
            collection_id = collections_svc.ensure_default_collection(
                service, username
            )["_key"]
        checklists_svc._require_collection(service, collection_id, session, write=True)
        host, created_host = _upsert_host(
            service, first, collection_id, username, session
        )
        if created_host:
            host_created += 1
        baseline, created_baseline = _upsert_baseline(service, batch, username)
        for event in batch:
            baselines_svc.ensure_baseline_rule(
                service, baseline["_key"], event.get("rule") or {}, event.get("stig")
            )
        existing = checklists_svc.find_checklist(
            service,
            session,
            collection_id,
            host["_key"],
            baseline["_key"],
        )
        target_data = (first.get("asset") or {}).get("target_data") or {}
        seeds = reviews_to_seeds(
            [
                {
                    "ruleId": event.get("ruleId"),
                    "groupId": event.get("groupId"),
                    "result": event.get("result"),
                    "detail": event.get("detail"),
                    "comment": event.get("comment"),
                }
                for event in batch
            ]
        )
        if existing:
            if target_data:
                current = parse_json_field(existing.get("target_data"), default={}) or {}
                if isinstance(current, dict):
                    merged = dict(current)
                    merged.update(target_data)
                    target_data = merged
                checklists_svc.update_checklist(
                    service,
                    existing["_key"],
                    {"target_data": target_data},
                    username,
                    session,
                )
            checklist = existing
            created = False
        else:
            checklist = checklists_svc.create_checklist(
                service,
                {
                    "stig_collection_id": collection_id,
                    "host_id": host["_key"],
                    "baseline_id": baseline["_key"],
                    "title": (first.get("stig") or {}).get("title")
                    or first.get("benchmarkId")
                    or "Checklist",
                    "target_data": target_data,
                },
                username,
                session,
                review_seeds=seeds,
            )
            created = True
            checklist_created += 1
        for event in batch:
            checklists_svc.ensure_review(
                service,
                checklist,
                event.get("rule") or {},
                username,
                seed=seeds.get(event.get("ruleId") or "")
                or seeds.get(event.get("groupId") or ""),
            )
        result = checklists_svc.apply_review_seeds(
            service, checklist["_key"], seeds, username, session
        )
        applied += int(result.get("updated") or 0)
        locked += int(result.get("locked") or 0)
        unmatched += int(result.get("unmatched") or 0)
        checklists.append(
            {
                "checklist_id": checklist["_key"],
                "created": created,
                "baseline_id": baseline["_key"],
                "baseline_created": created_baseline,
                "host_id": host["_key"],
                "hostname": host.get("hostname"),
                "benchmark_id": first.get("benchmarkId"),
                "review_count": len(batch),
                "reviews_applied": result.get("updated", 0),
                "reviews_locked": result.get("locked", 0),
                "reviews_unmatched": result.get("unmatched", 0),
            }
        )

    audit.log_event(
        "import",
        "stig_finding",
        (checklists[0].get("checklist_id") if checklists else "none"),
        username,
        {"applied": applied, "locked": locked, "checklists": len(checklists)},
    )
    return {
        "checklists": checklists,
        "host_created": host_created,
        "checklist_created": checklist_created,
        "applied": applied,
        "locked": locked,
        "unmatched": unmatched,
        "errors": errors,
        "finding_count": len(normalized),
    }
