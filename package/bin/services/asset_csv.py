"""Asset CSV import/export for a workspace (STIG Manager §2.9.2.2–2.9.2.3)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from exporters.asset_csv import (
    assets_to_csv,
    parse_asset_csv,
    parse_bool_non_computing,
    parse_metadata_cell,
    safe_asset_csv_filename,
    split_multiline_cell,
    _truncate,
)
from models import parse_json_field
from services import baselines as baselines_svc
from services import baseline_defaults as baseline_defaults_svc
from services import checklists as checklists_svc
from services import collection_metadata as coll_meta_svc
from services import grants as grants_svc
from services import hosts as hosts_svc
from services import labels as labels_svc


def _require_read(service, collection_id: str, session: Dict[str, Any]) -> None:
    grants_svc.require_workspace_read(service, collection_id, session)


def _require_write(service, collection_id: str, session: Dict[str, Any]) -> None:
    grants_svc.require_workspace_write(service, collection_id, session)


def _label_name_map(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, str]:
    rows = labels_svc.list_labels(service, collection_id, session)
    return {
        str(rec.get("_key")): (rec.get("name") or "").strip()
        for rec in rows
        if rec.get("_key")
    }


def _label_id_by_name(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, str]:
    rows = labels_svc.list_labels(service, collection_id, session)
    out: Dict[str, str] = {}
    for rec in rows:
        name = (rec.get("name") or "").strip().casefold()
        if name and rec.get("_key"):
            out[name] = str(rec["_key"])
    return out


def _host_metadata_dict(host: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return coll_meta_svc.parse_metadata_from_collection(host)
    except ValueError:
        return {}


def _metadata_for_csv(host: Dict[str, Any]) -> str:
    meta = _host_metadata_dict(host)
    if not meta:
        return ""
    # STIG Manager export uses string values only.
    slim = {str(k): str(v) for k, v in meta.items() if v is not None}
    if not slim:
        return ""
    return json.dumps(slim, separators=(",", ":"))


def _stigs_cell_for_host(
    service,
    host_id: str,
    checklists: List[Dict[str, Any]],
    baseline_cache: Dict[str, Dict[str, Any]],
) -> str:
    tokens: List[str] = []
    seen: Set[str] = set()
    for cl in checklists:
        if cl.get("host_id") != host_id:
            continue
        bid = (cl.get("baseline_id") or "").strip()
        if not bid:
            continue
        baseline = baseline_cache.get(bid)
        if baseline is None:
            baseline = baselines_svc.get_baseline(service, bid) or {}
            baseline_cache[bid] = baseline
        token = (
            (baseline.get("xccdf_benchmark_id") or "").strip()
            or (baseline.get("stig_id") or "").strip()
        )
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return "\n".join(tokens)


def export_assets_csv(
    service,
    collection_id: str,
    session: Dict[str, Any],
    host_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    _require_read(service, collection_id, session)
    hosts = hosts_svc.list_hosts(service, session, collection_id)
    want_ids = {str(x).strip() for x in (host_ids or []) if str(x).strip()}
    if want_ids:
        hosts = [h for h in hosts if h.get("_key") in want_ids]
    label_names = _label_name_map(service, collection_id, session)
    all_checklists = checklists_svc.list_checklists(service, session, collection_id)
    baseline_cache: Dict[str, Dict[str, Any]] = {}
    csv_rows: List[Dict[str, str]] = []
    for host in hosts:
        hid = host.get("_key") or ""
        label_ids = host.get("label_ids") or []
        if isinstance(label_ids, str):
            label_ids = parse_json_field(label_ids, default=[])
        label_cell = "\n".join(
            sorted(
                {
                    label_names.get(lid, "")
                    for lid in label_ids
                    if label_names.get(lid, "")
                }
            )
        )
        non_comp = (host.get("asset_type") or "").strip().casefold() == "non-computing"
        csv_rows.append(
            {
                "Name": host.get("hostname") or "",
                "Description": host.get("description") or "",
                "IP": host.get("ip_address") or "",
                "FQDN": host.get("fqdn") or "",
                "MAC": host.get("mac_address") or "",
                "Non-Computing": "TRUE" if non_comp else "FALSE",
                "STIGs": _stigs_cell_for_host(
                    service, hid, all_checklists, baseline_cache
                ),
                "Labels": label_cell,
                "Metadata": _metadata_for_csv(host),
            }
        )
    content = assets_to_csv(csv_rows)
    return {
        "format": "csv",
        "filename": safe_asset_csv_filename(collection_id),
        "content": content,
        "row_count": len(csv_rows),
        "stig_collection_id": collection_id,
    }


def _validate_row(
    service,
    collection_id: str,
    session: Dict[str, Any],
    row: Dict[str, Any],
    label_by_name: Dict[str, str],
    labels_to_create: Set[str],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    errors: List[str] = []
    name = _truncate(str(row.get("Name") or "").strip(), 255)
    if not name:
        errors.append("Name is required")
    elif len(name) > 255:
        errors.append("Name must be at most 255 characters")

    description = _truncate(str(row.get("Description") or "").strip(), 255)
    ip = _truncate(str(row.get("IP") or "").strip(), 255)
    fqdn = _truncate(str(row.get("FQDN") or "").strip(), 255)
    mac = _truncate(str(row.get("MAC") or "").strip(), 255)

    try:
        non_comp = parse_bool_non_computing(str(row.get("Non-Computing") or ""))
    except ValueError as exc:
        errors.append(str(exc))
        non_comp = False

    metadata: Optional[Dict[str, str]] = None
    meta_cell = str(row.get("Metadata") or "").strip()
    if meta_cell:
        try:
            metadata = parse_metadata_cell(meta_cell)
        except ValueError as exc:
            errors.append(str(exc))

    stig_tokens = split_multiline_cell(str(row.get("STIGs") or ""))
    resolved_stigs: List[str] = []
    for token in stig_tokens:
        bid = baseline_defaults_svc.resolve_baseline_id(
            service,
            collection_id=collection_id,
            stig_id=token,
            xccdf_benchmark_id=token,
        )
        if not bid:
            errors.append(f"STIG not installed: {token}")
        else:
            resolved_stigs.append(bid)

    label_names = split_multiline_cell(str(row.get("Labels") or ""))
    label_ids: List[str] = []
    for label_name in label_names:
        key = label_name.casefold()
        lid = label_by_name.get(key)
        if lid:
            label_ids.append(lid)
        else:
            labels_to_create.add(label_name)

    parsed = {
        "hostname": name,
        "description": description,
        "ip_address": ip,
        "fqdn": fqdn,
        "mac_address": mac,
        "asset_type": "Non-Computing" if non_comp else "Computing",
        "metadata": metadata,
        "baseline_ids": resolved_stigs,
        "label_names": label_names,
        "label_ids": label_ids,
    }
    return (len(errors) == 0, errors, parsed)


def import_assets_csv(
    service,
    collection_id: str,
    csv_text: str,
    username: str,
    session: Dict[str, Any],
    *,
    submit: bool = False,
) -> Dict[str, Any]:
    _require_write(service, collection_id, session)
    try:
        rows = parse_asset_csv(csv_text)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    label_by_name = _label_id_by_name(service, collection_id, session)
    labels_to_create: Set[str] = set()
    report_rows: List[Dict[str, Any]] = []
    valid_parsed: List[Dict[str, Any]] = []

    for row in rows:
        row_num = int(row.get("_row") or 0)
        ok, errors, parsed = _validate_row(
            service, collection_id, session, row, label_by_name, labels_to_create
        )
        report_rows.append(
            {
                "row": row_num,
                "name": parsed.get("hostname") or "",
                "valid": ok,
                "errors": errors,
            }
        )
        if ok:
            valid_parsed.append({"row": row_num, **parsed})

    valid_count = len(valid_parsed)
    invalid_count = len(report_rows) - valid_count

    summary = {
        "created": 0,
        "updated": 0,
        "stigs_assigned": 0,
        "labels_created": 0,
    }

    if not submit:
        return {
            "submitted": False,
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "labels_pending_create": sorted(labels_to_create),
            "rows": report_rows,
            "summary": summary,
        }

    if valid_count == 0:
        return {
            "submitted": True,
            "valid_count": 0,
            "invalid_count": invalid_count,
            "rows": report_rows,
            "summary": summary,
        }

    for label_name in sorted(labels_to_create):
        created = labels_svc.create_label(
            service,
            collection_id,
            {"name": label_name},
            username,
            session,
        )
        label_by_name[label_name.casefold()] = str(created["_key"])
        summary["labels_created"] += 1

    for item in valid_parsed:
        row_num = item["row"]
        name = item["hostname"]
        existing = hosts_svc.find_host_by_hostname(service, session, collection_id, name)
        label_ids = list(item.get("label_ids") or [])
        for label_name in item.get("label_names") or []:
            lid = label_by_name.get(label_name.casefold())
            if lid and lid not in label_ids:
                label_ids.append(lid)

        body = {
            "stig_collection_id": collection_id,
            "hostname": name,
            "description": item.get("description") or "",
            "ip_address": item.get("ip_address") or "",
            "fqdn": item.get("fqdn") or "",
            "mac_address": item.get("mac_address") or "",
            "asset_type": item.get("asset_type") or "Computing",
            "label_ids": label_ids,
        }
        if item.get("metadata") is not None:
            body["metadata"] = item.get("metadata") or {}

        if existing:
            host_id = existing["_key"]
            patch = dict(body)
            patch.pop("stig_collection_id", None)
            stored = hosts_svc.update_host(
                service, host_id, patch, username, session
            )
            action = "updated"
            summary["updated"] += 1
        else:
            stored = hosts_svc.create_host(service, body, username, session)
            host_id = stored["_key"]
            action = "created"
            summary["created"] += 1

        for baseline_id in item.get("baseline_ids") or []:
            _cl, created = checklists_svc.assign_stig_to_host(
                service,
                host_id,
                {"baseline_id": baseline_id},
                username,
                session,
            )
            summary["stigs_assigned"] += 1

        for rep in report_rows:
            if rep.get("row") == row_num:
                rep["host_id"] = host_id
                rep["action"] = action
                break

    return {
        "submitted": True,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "rows": report_rows,
        "summary": summary,
    }
