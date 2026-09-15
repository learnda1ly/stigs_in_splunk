"""Parse CKLB JSON for baseline import or Watcher-shaped checklist ingest."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from importers import ingest as ingest_lib
from models import check_content_hash, normalize_status


def parse_cklb_baseline(content: str | bytes, source_uri: str = "") -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    doc = json.loads(content)
    stigs = doc.get("stigs") or []
    if not stigs:
        raise ValueError("CKLB has no stigs array")

    stig = stigs[0]
    meta: Dict[str, Any] = {
        "stig_id": stig.get("stig_id") or "unknown_stig",
        "title": doc.get("title") or stig.get("stig_name") or "",
        "stig_name": stig.get("stig_name") or doc.get("title") or "",
        "version": str(stig.get("version") or ""),
        "release_info": stig.get("release_info") or "",
        "benchmark_date": "",
        "xccdf_benchmark_id": "",
        "source_type": "cklb",
        "source_uri": source_uri,
    }

    rules: List[Dict[str, Any]] = []
    for rule in stig.get("rules") or []:
        check_text = rule.get("check_content") or ""
        rules.append(
            {
                "group_id": rule.get("group_id") or "",
                "rule_id": rule.get("rule_id") or rule.get("rule_id_src") or "",
                "rule_id_src": rule.get("rule_id_src") or rule.get("rule_id") or "",
                "rule_version": rule.get("rule_version") or "",
                "severity": (rule.get("severity") or "medium").lower(),
                "rule_title": rule.get("rule_title") or "",
                "discussion": rule.get("discussion") or "",
                "check_content": check_text,
                "fix_text": rule.get("fix_text") or "",
                "ccis": rule.get("ccis") or [],
                "check_content_hash": check_content_hash(check_text),
                "group_title": "",
            }
        )

    meta["rule_count"] = len(rules)
    return meta, rules


def parse_cklb_reviews(stig: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map group_id -> review fields from a CKLB stig block."""
    out: Dict[str, Dict[str, Any]] = {}
    for rule in stig.get("rules") or []:
        gid = rule.get("group_id")
        if not gid:
            continue
        status = normalize_status(rule.get("status"), source="cklb") or "not_reviewed"
        out[gid] = {
            "status": status,
            "finding_details": rule.get("finding_details") or "",
            "comments": rule.get("comments") or "",
        }
    return out


def _stig_to_baseline(
    stig: Dict[str, Any], doc: Dict[str, Any], source_uri: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    stig_id = str(stig.get("stig_id") or "unknown_stig").replace(
        "xccdf_mil.disa.stig_benchmark_", ""
    )
    meta: Dict[str, Any] = {
        "stig_id": stig_id or "unknown_stig",
        "title": doc.get("title") or stig.get("stig_name") or "",
        "stig_name": stig.get("stig_name") or doc.get("title") or "",
        "version": str(stig.get("version") or ""),
        "release_info": stig.get("release_info") or "",
        "benchmark_date": "",
        "xccdf_benchmark_id": "",
        "source_type": "cklb",
        "source_uri": source_uri,
        "uuid": stig.get("uuid") or "",
        "display_name": stig.get("display_name") or "",
        "reference_identifier": stig.get("reference_identifier") or "",
    }
    rules: List[Dict[str, Any]] = []
    for rule in stig.get("rules") or []:
        check_text = rule.get("check_content") or ""
        rules.append(
            {
                "group_id": rule.get("group_id") or "",
                "rule_id": rule.get("rule_id") or rule.get("rule_id_src") or "",
                "rule_id_src": rule.get("rule_id_src") or rule.get("rule_id") or "",
                "rule_version": rule.get("rule_version") or "",
                "severity": (rule.get("severity") or "medium").lower(),
                "rule_title": rule.get("rule_title") or "",
                "discussion": rule.get("discussion") or "",
                "check_content": check_text,
                "fix_text": rule.get("fix_text") or "",
                "ccis": rule.get("ccis") or [],
                "check_content_hash": check_content_hash(check_text),
                "group_title": rule.get("group_title") or "",
            }
        )
    meta["rule_count"] = len(rules)
    return meta, rules


def parse_cklb_target(doc: Dict[str, Any]) -> Dict[str, Any]:
    td = doc.get("target_data") or {}
    host_name = td.get("host_name") or ""
    metadata: Dict[str, Any] = {}
    if td.get("role"):
        metadata["cklRole"] = td.get("role")
    if td.get("technology_area"):
        metadata["cklTechArea"] = td.get("technology_area")
    if td.get("is_web_database"):
        metadata["cklWebOrDatabase"] = "true"
        metadata["cklHostName"] = host_name
        if td.get("web_db_site"):
            metadata["cklWebDbSite"] = td.get("web_db_site")
        if td.get("web_db_instance"):
            metadata["cklWebDbInstance"] = td.get("web_db_instance")
    return {
        "name": ingest_lib.truncate(host_name, ingest_lib.MAX_NAME_LENGTH) or "",
        "description": ingest_lib.truncate(td.get("comments"), ingest_lib.MAX_NAME_LENGTH),
        "ip": ingest_lib.truncate(td.get("ip_address"), ingest_lib.MAX_NAME_LENGTH) or None,
        "fqdn": ingest_lib.truncate(td.get("fqdn"), ingest_lib.MAX_NAME_LENGTH) or None,
        "mac": ingest_lib.truncate(td.get("mac_address"), ingest_lib.MAX_NAME_LENGTH) or None,
        "noncomputing": td.get("target_type") == "Non-Computing",
        "metadata": metadata,
    }


def parse_cklb_ingest(content: str | bytes, source_uri: str = "") -> Dict[str, Any]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    try:
        doc = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ValueError("Cannot parse as JSON") from exc
    if not isinstance(doc, dict):
        raise ValueError("Invalid CKLB object: expected a JSON object")
    td = doc.get("target_data") or {}
    if not td.get("host_name"):
        raise ValueError("Invalid CKLB object: No target_data.host_name found")
    stigs = doc.get("stigs")
    if not isinstance(stigs, list):
        raise ValueError("Invalid CKLB object: No stigs array found")
    if not stigs:
        raise ValueError("stigs array is empty")

    target = parse_cklb_target(doc)
    if not target.get("name"):
        raise ValueError("No host_name in target_data")
    if len(target["name"]) > ingest_lib.MAX_NAME_LENGTH:
        raise ValueError("Asset hostname cannot be more than 255 characters")

    checklists: List[Dict[str, Any]] = []
    for stig in stigs:
        meta, rules = _stig_to_baseline(stig or {}, doc, source_uri)
        benchmark_id = meta.get("stig_id") or ""
        if not benchmark_id or benchmark_id == "unknown_stig":
            continue
        reviews: List[Dict[str, Any]] = []
        stats = ingest_lib.empty_stats()
        for rule in stig.get("rules") or []:
            rule_id = rule.get("rule_id_src") or rule.get("rule_id") or ""
            result = ingest_lib.result_from_status(rule.get("status"), source="cklb")
            if not rule_id or not result:
                continue
            review = ingest_lib.streamed_review(
                rule_id=rule_id,
                result=result,
                detail=rule.get("finding_details") or "",
                comment=rule.get("comments") or "",
                status="saved",
                group_id=rule.get("group_id") or "",
            )
            reviews.append(review)
            ingest_lib.tally_result(stats, review.get("result"))
        checklists.append(
            {
                "sourceRef": source_uri,
                "benchmarkId": ingest_lib.truncate(benchmark_id, ingest_lib.MAX_NAME_LENGTH)
                or benchmark_id,
                "revisionStr": ingest_lib.revision_str(
                    meta.get("version"), meta.get("release_info")
                ),
                "reviews": reviews,
                "stats": stats,
                "baseline_meta": meta,
                "baseline_rules": rules,
                "target_data": td,
            }
        )

    if not checklists:
        raise ValueError("stigs array is empty")

    return {
        "sourceRef": source_uri,
        "target": target,
        "checklists": checklists,
        "errors": [],
        "target_data": td,
    }
