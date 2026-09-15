"""stig_checklists CRUD, review spawn, export."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import base64
import io
import re
import zipfile

import access
import audit
import kv_client
import validation
from exporters import ckl as ckl_export
from exporters import cklb as cklb_export
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_REVIEWS,
    dumps_json,
    is_ingest_locked,
    kv_record,
    new_id,
    now_epoch,
    parse_json_field,
)
from importers.ingest import match_review_seed
from services import baselines as baselines_svc
from services import collections as collections_svc
from services import hosts as hosts_svc


def _require_collection(service, collection_id: str, session: Dict[str, Any], write: bool = False):
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    ok = access.user_can_write_collection(rec, session) if write else access.user_can_read_collection(rec, session)
    if not ok:
        raise PermissionError("access denied to stig_collection")


def list_checklists(
    service, session: Dict[str, Any], stig_collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    query = {"stig_collection_id": stig_collection_id} if stig_collection_id else {}
    records = kv_client.query_all(coll, query)
    if stig_collection_id:
        _require_collection(service, stig_collection_id, session)
        return records
    allowed = {r["_key"] for r in collections_svc.list_collections(service, session)}
    return [r for r in records if r.get("stig_collection_id") in allowed]


def get_checklist(
    service, key: str, session: Dict[str, Any], write: bool = False
) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    rec = kv_client.get_by_key(coll, key)
    if rec:
        _require_collection(service, rec["stig_collection_id"], session, write=write)
    return rec


def find_checklist(
    service,
    session: Dict[str, Any],
    stig_collection_id: str,
    host_id: str,
    baseline_id: str,
) -> Optional[Dict[str, Any]]:
    for rec in list_checklists(service, session, stig_collection_id):
        if rec.get("host_id") == host_id and rec.get("baseline_id") == baseline_id:
            return rec
    return None


def apply_review_seeds(
    service,
    checklist_id: str,
    seeds: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, int]:
    get_checklist(service, checklist_id, session, write=True)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    records = kv_client.query_all(reviews_coll, {"checklist_id": checklist_id})
    updated = 0
    unmatched = 0
    locked = 0
    ts = now_epoch()
    for rec in records:
        seed = match_review_seed(rec, seeds)
        if not seed:
            unmatched += 1
            continue
        if is_ingest_locked(rec):
            locked += 1
            continue
        patch = dict(rec)
        if "status" in seed:
            patch["status"] = seed["status"]
        if "finding_details" in seed:
            patch["finding_details"] = seed["finding_details"] or ""
        if "comments" in seed:
            patch["comments"] = seed["comments"] or ""
        patch["valid"] = validation.persistable_valid(patch)
        patch["updated_at"] = ts
        patch["updated_by"] = username
        kv_client.update_record(reviews_coll, rec["_key"], kv_record(patch))
        updated += 1
    return {"updated": updated, "unmatched": unmatched, "locked": locked}


def create_checklist(
    service,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
    review_seeds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    collection_id = body.get("stig_collection_id")
    host_id = body.get("host_id")
    baseline_id = body.get("baseline_id")
    if not all([collection_id, host_id, baseline_id]):
        raise ValueError("stig_collection_id, host_id, and baseline_id are required")

    _require_collection(service, collection_id, session, write=True)
    host = hosts_svc.get_host(service, host_id, session)
    if not host or host.get("stig_collection_id") != collection_id:
        raise ValueError("host not found in stig_collection")
    baseline = baselines_svc.get_baseline(service, baseline_id)
    if not baseline:
        raise KeyError(baseline_id)

    rules = baselines_svc.list_baseline_rules(service, baseline_id)
    if not rules:
        raise ValueError("baseline has no rules")

    checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    duplicates = [
        c
        for c in kv_client.query_all(
            checklist_coll,
            {
                "stig_collection_id": collection_id,
                "host_id": host_id,
                "baseline_id": baseline_id,
            },
        )
    ]
    if duplicates:
        raise ValueError("a checklist already exists for this host and baseline")

    target_data = {
        "host_name": host.get("hostname") or "",
        "ip_address": host.get("ip_address") or "",
        "fqdn": host.get("fqdn") or "",
        "mac_address": host.get("mac_address") or "",
        "role": host.get("role") or "None",
        "asset_type": host.get("asset_type") or "Computing",
    }
    if body.get("target_data"):
        target_data.update(body["target_data"])

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)

    ts = now_epoch()
    title = body.get("title") or baseline.get("title") or "Checklist"
    checklist_record = kv_record(
        {
            "stig_collection_id": collection_id,
            "host_id": host_id,
            "baseline_id": baseline_id,
            "title": title,
            "mode": int(body.get("mode") or 1),
            "target_data": dumps_json(target_data),
            "created_at": ts,
            "updated_at": ts,
            "created_by": username,
            "updated_by": username,
        }
    )
    stored_checklist = kv_client.insert_record(checklist_coll, checklist_record)
    checklist_id = stored_checklist["_key"]

    review_records = []
    for rule in rules:
        seed = match_review_seed(rule, review_seeds)
        review = {
            "checklist_id": checklist_id,
            "baseline_id": baseline_id,
            "group_id": rule.get("group_id"),
            "rule_id": rule.get("rule_id"),
            "rule_version": rule.get("rule_version"),
            "check_content_hash": rule.get("check_content_hash"),
            "status": seed.get("status") or "not_reviewed",
            "finding_details": seed.get("finding_details") or "",
            "comments": seed.get("comments") or "",
            "package_id": "",
            "ingest_lock": False,
            "updated_at": ts,
            "updated_by": username,
        }
        review["valid"] = validation.persistable_valid(review)
        review_records.append(kv_record(review))
    kv_client.batch_insert(reviews_coll, review_records)

    audit.log_event(
        "create",
        "stig_checklist",
        checklist_id,
        username,
        {"reviews": len(review_records)},
    )
    return stored_checklist


def ensure_review(
    service,
    checklist: Dict[str, Any],
    rule: Dict[str, Any],
    username: str,
    seed: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    checklist_id = checklist.get("_key") or ""
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    records = kv_client.query_all(reviews_coll, {"checklist_id": checklist_id})
    want = {
        str(rule.get("rule_id") or ""),
        str(rule.get("rule_id_src") or ""),
        str(rule.get("group_id") or ""),
    }
    want.discard("")
    for rec in records:
        keys = {str(rec.get("rule_id") or ""), str(rec.get("group_id") or "")}
        keys.discard("")
        if keys.intersection(want):
            return rec, False
    seed = seed or {}
    ts = now_epoch()
    review = {
        "checklist_id": checklist_id,
        "baseline_id": checklist.get("baseline_id"),
        "group_id": rule.get("group_id"),
        "rule_id": rule.get("rule_id"),
        "rule_version": rule.get("rule_version"),
        "check_content_hash": rule.get("check_content_hash"),
        "status": seed.get("status") or "not_reviewed",
        "finding_details": seed.get("finding_details") or "",
        "comments": seed.get("comments") or "",
        "package_id": "",
        "ingest_lock": False,
        "updated_at": ts,
        "updated_by": username,
    }
    review["valid"] = validation.persistable_valid(review)
    stored = kv_client.insert_record(reviews_coll, kv_record(review))
    return stored, True


def update_checklist(
    service, key: str, body: Dict[str, Any], username: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection(service, existing["stig_collection_id"], session, write=True)

    patch = dict(existing)
    if "title" in body:
        patch["title"] = body["title"]
    if "mode" in body:
        patch["mode"] = int(body["mode"])
    if "target_data" in body:
        val = body["target_data"]
        patch["target_data"] = dumps_json(val) if isinstance(val, dict) else val
    patch["updated_at"] = now_epoch()
    patch["updated_by"] = username
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event("update", "stig_checklist", key, username, body)
    return stored


def delete_checklist(service, key: str, username: str, session: Dict[str, Any]) -> None:
    coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    existing = kv_client.get_by_key(coll, key)
    if not existing:
        raise KeyError(key)
    _require_collection(service, existing["stig_collection_id"], session, write=True)

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    for review in kv_client.query_all(reviews_coll, {"checklist_id": key}):
        kv_client.delete_record(reviews_coll, review["_key"])
    kv_client.delete_record(coll, key)
    audit.log_event("delete", "stig_checklist", key, username)


def export_checklist(
    service, key: str, fmt: str, session: Dict[str, Any]
) -> str:
    checklist = get_checklist(service, key, session)
    if not checklist:
        raise KeyError(key)
    baseline = baselines_svc.get_baseline(service, checklist["baseline_id"])
    if not baseline:
        raise KeyError(checklist["baseline_id"])
    host = hosts_svc.get_host(service, checklist["host_id"], session)
    if not host:
        raise KeyError(checklist["host_id"])

    rules = baselines_svc.list_baseline_rules(service, checklist["baseline_id"])
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    reviews = kv_client.query_all(reviews_coll, {"checklist_id": key})
    reviews_by_group = {r.get("group_id"): r for r in reviews if r.get("group_id")}
    for rec in reviews:
        if rec.get("rule_id"):
            reviews_by_group.setdefault(rec["rule_id"], rec)
        if rec.get("rule_version"):
            reviews_by_group.setdefault(rec["rule_version"], rec)

    export_fmt = (fmt or "cklb").lower()
    if export_fmt == "ckl":
        return ckl_export.export_ckl(checklist, baseline, rules, reviews, host)
    return cklb_export.export_cklb(checklist, baseline, rules, reviews, host)


def _safe_filename_part(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return text.strip("._") or "item"


def export_filename(
    checklist: Dict[str, Any],
    baseline: Dict[str, Any],
    host: Dict[str, Any],
    fmt: str,
) -> str:
    host_part = _safe_filename_part(host.get("hostname") or checklist.get("_key"))
    stig_part = _safe_filename_part(
        baseline.get("stig_id") or baseline.get("title") or "stig"
    )
    version = _safe_filename_part(baseline.get("version") or "")
    ext = "ckl" if (fmt or "").lower() == "ckl" else "cklb"
    name = f"{host_part}_{stig_part}"
    if version:
        name += f"_{version}"
    return f"{name}.{ext}"


def export_checklist_file(
    service, key: str, fmt: str, session: Dict[str, Any]
) -> Tuple[str, str]:
    checklist = get_checklist(service, key, session)
    if not checklist:
        raise KeyError(key)
    baseline = baselines_svc.get_baseline(service, checklist["baseline_id"])
    if not baseline:
        raise KeyError(checklist["baseline_id"])
    host = hosts_svc.get_host(service, checklist["host_id"], session)
    if not host:
        raise KeyError(checklist["host_id"])
    content = export_checklist(service, key, fmt, session)
    return content, export_filename(checklist, baseline, host, fmt)


def export_checklists_bulk(
    service,
    checklist_ids: List[str],
    fmt: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    ids = [str(i).strip() for i in checklist_ids or [] if str(i).strip()]
    if not ids:
        raise ValueError("checklist_ids is required")
    export_fmt = (fmt or "cklb").lower()
    if export_fmt not in {"ckl", "cklb"}:
        raise ValueError("format must be ckl or cklb")

    buf = io.BytesIO()
    files: List[str] = []
    used: Dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for key in ids:
            content, filename = export_checklist_file(service, key, export_fmt, session)
            count = used.get(filename, 0)
            used[filename] = count + 1
            if count:
                stem, ext = filename.rsplit(".", 1)
                filename = f"{stem}_{count + 1}.{ext}"
            archive.writestr(filename, content)
            files.append(filename)

    zip_name = f"stig-checklists-{export_fmt}.zip"
    return {
        "filename": zip_name,
        "format": export_fmt,
        "count": len(files),
        "files": files,
        "content_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def _by_key(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for rec in records or []:
        key = rec.get("_key")
        if key:
            out[str(key)] = rec
    return out


def summarize_checklists(
    service, session: Dict[str, Any], stig_collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    checklists = list_checklists(service, session, stig_collection_id)
    collections = _by_key(collections_svc.list_collections(service, session))
    host_query = stig_collection_id or None
    try:
        hosts = _by_key(hosts_svc.list_hosts(service, session, host_query))
    except Exception:
        hosts = {}
    try:
        baselines = _by_key(baselines_svc.list_baselines(service))
    except Exception:
        baselines = {}

    reviews_by_checklist: Dict[str, List[Dict[str, Any]]] = {}
    try:
        reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
        for checklist in checklists:
            key = checklist.get("_key")
            if not key:
                continue
            reviews_by_checklist[key] = kv_client.query_all(
                reviews_coll, {"checklist_id": key}
            )
    except Exception:
        reviews_by_checklist = {}

    summaries: List[Dict[str, Any]] = []
    for checklist in checklists:
        reviews = reviews_by_checklist.get(checklist.get("_key"), [])
        host = hosts.get(checklist.get("host_id"), {})
        baseline = baselines.get(checklist.get("baseline_id"), {})
        collection = collections.get(checklist.get("stig_collection_id"), {})
        package_ids = sorted(
            {
                str(review.get("package_id") or "").strip()
                for review in reviews
                if str(review.get("package_id") or "").strip()
            }
        )
        summaries.append(
            {
                "_key": checklist.get("_key"),
                "title": checklist.get("title"),
                "stig_collection_id": checklist.get("stig_collection_id"),
                "collection_name": collection.get("name") or "",
                "host_id": checklist.get("host_id"),
                "hostname": host.get("hostname") or "",
                "baseline_id": checklist.get("baseline_id"),
                "baseline_title": baseline.get("title") or "",
                "stig_id": baseline.get("stig_id") or "",
                "baseline_version": baseline.get("version") or "",
                "review_count": len(reviews),
                "valid_count": sum(1 for review in reviews if validation.is_valid(review)),
                "package_ids": package_ids,
            }
        )
    summaries.sort(
        key=lambda row: (
            row.get("collection_name") or "",
            row.get("hostname") or "",
            row.get("stig_id") or "",
        )
    )
    return summaries
