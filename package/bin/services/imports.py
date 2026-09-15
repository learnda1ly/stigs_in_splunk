"""Bulk CKL/CKLB checklist import: index via HEC, then apply to KV."""

from __future__ import annotations

from typing import Any, Dict

import audit
from importers.events import events_from_parsed
from importers.ingest import parse_ingest
from services import apply as apply_svc
from services import collections as collections_svc
from services import hec as hec_svc
from services import settings as settings_svc


def _collection_name(service, session: Dict[str, Any], collection_id: str) -> str:
    rec = collections_svc.get_collection(service, collection_id)
    return (rec or {}).get("name") or ""


def import_checklist_file(
    service,
    body: bytes,
    format_name: str,
    username: str,
    session: Dict[str, Any],
    stig_collection_id: str,
    source_uri: str = "",
) -> Dict[str, Any]:
    if not stig_collection_id:
        stig_collection_id = collections_svc.ensure_default_collection(
            service, username
        )["_key"]
    if not body:
        raise ValueError("empty import body")

    parsed = parse_ingest(format_name, body, source_uri)
    target = parsed.get("target") or {}
    if not target.get("name"):
        raise ValueError("checklist has no host_name")

    source_product = "evaluate-stig"
    if any(
        (review.get("resultEngine") or {}).get("product") == "Evaluate-STIG"
        for checklist in parsed.get("checklists") or []
        for review in checklist.get("reviews") or []
    ):
        source_product = "evaluate-stig"
    elif (format_name or "").lower() in {"ckl", "cklb"}:
        source_product = "stigman-watcher"

    findings = events_from_parsed(
        parsed,
        stig_collection_id,
        source_uri=source_uri,
        source_product=source_product,
        collection_name=_collection_name(service, session, stig_collection_id),
    )
    settings = settings_svc.get_settings(service)
    indexed = hec_svc.emit_findings(
        findings,
        settings=settings,
        session_key=(session or {}).get("authtoken") or "",
        source=source_uri or "stigs_in_splunk",
    )
    applied = apply_svc.apply_finding_events(service, findings, username, session)

    totals = {"pass": 0, "fail": 0, "notapplicable": 0, "notchecked": 0}
    for checklist in parsed.get("checklists") or []:
        stats = checklist.get("stats") or {}
        for key in totals:
            totals[key] += int(stats.get(key) or 0)

    first = (applied.get("checklists") or [{}])[0]
    audit.log_event(
        "import",
        "stig_checklist",
        first.get("host_id") or stig_collection_id,
        username,
        {
            "source_uri": source_uri,
            "format": format_name,
            "findings": len(findings),
            "indexed": indexed.get("indexed"),
            "locked": applied.get("locked"),
        },
    )
    return {
        "source_uri": source_uri,
        "format": format_name,
        "target": target,
        "host": {
            "_key": first.get("host_id") or "",
            "hostname": first.get("hostname") or target.get("name"),
            "created": bool(applied.get("host_created")),
        },
        "checklists": applied.get("checklists") or [],
        "stats": totals,
        "finding_count": len(findings),
        "findings": findings,
        "indexed": indexed,
        "applied": applied.get("applied", 0),
        "locked": applied.get("locked", 0),
        "errors": (parsed.get("errors") or []) + (applied.get("errors") or []),
    }
