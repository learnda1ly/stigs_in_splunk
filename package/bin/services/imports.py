"""Bulk CKL/CKLB checklist import: index via HEC, then apply to KV."""

from __future__ import annotations

import base64
from typing import Any, Dict, List

import audit
from importers.checklist_zip import checklist_format, list_checklist_files
from importers.events import events_from_parsed
from importers.ingest import detect_format, parse_ingest
from services import apply as apply_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import hec as hec_svc
from services import settings as settings_svc

MAX_BATCH_FILES = 500


def _collection_name(service, session: Dict[str, Any], collection_id: str) -> str:
    rec = collections_svc.get_collection(service, collection_id)
    return (rec or {}).get("name") or ""


def resolve_import_workspace(
    service,
    session: Dict[str, Any],
    username: str,
    collection_id: str = "",
) -> str:
    """Resolve target workspace and require write access (collection import builder)."""
    cid = (collection_id or "").strip()
    if not cid:
        default = collections_svc.ensure_default_collection(service, username)
        cid = (default or {}).get("_key") or ""
    if not cid or not collections_svc.get_collection(service, cid):
        raise KeyError(collection_id or cid or "workspace")
    grants_svc.require_workspace_write(service, cid, session)
    return cid


def _entry_created(rec: Dict[str, Any]) -> bool:
    host = rec.get("host") or {}
    if host.get("created"):
        return True
    return any(item.get("created") for item in rec.get("checklists") or [])


def _public_import_row(rec: Dict[str, Any], *, status: str = "ok", error: str = "") -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "source_uri": rec.get("source_uri") or "",
        "format": rec.get("format") or "",
        "status": status,
    }
    if error:
        row["error"] = error
        return row
    row["host"] = rec.get("host") or {}
    row["checklists"] = [
        {
            "_key": item.get("_key") or item.get("checklist_id"),
            "baseline_id": item.get("baseline_id"),
            "created": bool(item.get("created")),
        }
        for item in rec.get("checklists") or []
    ]
    row["stats"] = rec.get("stats") or {}
    row["finding_count"] = int(rec.get("finding_count") or 0)
    row["created"] = _entry_created(rec)
    errors = rec.get("errors") or []
    if errors:
        row["errors"] = errors
    return row


def import_checklist_file(
    service,
    body: bytes,
    format_name: str,
    username: str,
    session: Dict[str, Any],
    stig_collection_id: str,
    source_uri: str = "",
    operator_collection_id: str = "",
) -> Dict[str, Any]:
    forced_collection_id = (operator_collection_id or stig_collection_id or "").strip()
    if not forced_collection_id:
        stig_collection_id = ""
    else:
        stig_collection_id = forced_collection_id
        grants_svc.require_workspace_write(service, stig_collection_id, session)
    if not body:
        raise ValueError("empty import body")

    parsed = parse_ingest(format_name, body, source_uri)
    target = parsed.get("target") or {}
    if not target.get("name"):
        raise ValueError("checklist has no host_name")

    fmt_lower = (format_name or "").lower()
    source_product = "evaluate-stig"
    if fmt_lower in {"xccdf-results", "xccdf_results", "xccdfresults"}:
        source_product = "xccdf-results"
    elif any(
        (review.get("resultEngine") or {}).get("product") == "Evaluate-STIG"
        for checklist in parsed.get("checklists") or []
        for review in checklist.get("reviews") or []
    ):
        source_product = "evaluate-stig"
    elif fmt_lower in {"ckl", "cklb"}:
        source_product = "stigman-watcher"

    collection_name = (
        _collection_name(service, session, stig_collection_id) if stig_collection_id else ""
    )
    findings = events_from_parsed(
        parsed,
        stig_collection_id,
        source_uri=source_uri,
        source_product=source_product,
        collection_name=collection_name,
    )
    settings = settings_svc.get_settings(service)
    indexed = hec_svc.emit_findings(
        findings,
        settings=settings,
        session_key=(session or {}).get("authtoken") or "",
        source=source_uri or "stigs_in_splunk",
    )
    applied = apply_svc.apply_finding_events(
        service,
        findings,
        username,
        session,
        forced_collection_id=forced_collection_id,
    )

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


def _decode_entry_body(entry: Dict[str, Any]) -> bytes:
    if entry.get("content_base64"):
        try:
            return base64.b64decode(str(entry.get("content_base64") or ""), validate=True)
        except (TypeError, ValueError) as err:
            raise ValueError(f"invalid content_base64: {err}") from err
    content = entry.get("content")
    if content is None:
        raise ValueError("entry requires content or content_base64")
    if isinstance(content, bytes):
        return content
    return str(content).encode("utf-8")


def import_checklist_batch(
    service,
    session: Dict[str, Any],
    username: str,
    collection_id: str,
    entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cid = resolve_import_workspace(service, session, username, collection_id)
    files = list(entries or [])
    if not files:
        raise ValueError("files array is required")
    if len(files) > MAX_BATCH_FILES:
        raise ValueError(f"batch exceeds {MAX_BATCH_FILES} files")

    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    created = 0
    for entry in files:
        source_uri = (entry.get("source_uri") or entry.get("name") or "").strip()
        try:
            body = _decode_entry_body(entry)
            fmt = (entry.get("format") or "").strip().lower()
            if not fmt:
                fmt = detect_format(source_uri, body)
            if fmt not in {"ckl", "cklb"}:
                raise ValueError("format must be ckl or cklb for collection import builder")
            rec = import_checklist_file(
                service,
                body,
                fmt,
                username,
                session,
                cid,
                source_uri=source_uri,
                operator_collection_id=cid,
            )
            row = _public_import_row(rec)
            results.append(row)
            succeeded += 1
            if row.get("created"):
                created += 1
        except Exception as exc:
            failed += 1
            results.append(
                {
                    "source_uri": source_uri,
                    "format": entry.get("format") or "",
                    "status": "error",
                    "error": str(exc),
                }
            )
    return {
        "stig_collection_id": cid,
        "results": results,
        "summary": {
            "total": len(files),
            "succeeded": succeeded,
            "failed": failed,
            "created": created,
            "updated": max(0, succeeded - created),
        },
    }


def import_checklist_zip(
    service,
    session: Dict[str, Any],
    username: str,
    collection_id: str,
    body: bytes,
    source_uri: str = "",
) -> Dict[str, Any]:
    if not body:
        raise ValueError("empty zip body")
    members = list_checklist_files(body, source_prefix=source_uri or "archive.zip")
    if not members:
        raise ValueError("zip contains no .ckl or .cklb checklist files")
    entries = []
    for path, raw in members:
        entries.append(
            {
                "source_uri": path,
                "format": checklist_format(path),
                "content": raw,
            }
        )
    batch = import_checklist_batch(service, session, username, collection_id, entries)
    batch["archive"] = {
        "source_uri": source_uri or "archive.zip",
        "member_count": len(members),
    }
    return batch
