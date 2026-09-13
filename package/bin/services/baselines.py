"""stig_baselines import and read."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import audit
import kv_client
from importers import ckl, cklb, xccdf
from models import (
    KV_STIG_BASELINES,
    KV_STIG_BASELINE_RULES,
    baseline_content_fingerprint,
    dumps_json,
    kv_record,
    now_epoch,
)


def list_baselines(service) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_BASELINES)
    return kv_client.query_all(coll)


def get_baseline(service, key: str) -> Optional[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_BASELINES)
    return kv_client.get_by_key(coll, key)


def list_baseline_rules(service, baseline_id: str) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)
    return kv_client.query_all(coll, {"baseline_id": baseline_id})


def find_baseline_by_fingerprint(
    service, content_fingerprint: str
) -> Optional[Dict[str, Any]]:
    if not content_fingerprint:
        return None
    coll = kv_client.get_collection(service, KV_STIG_BASELINES)
    matches = kv_client.query_all(
        coll, {"content_fingerprint": content_fingerprint}
    )
    if not matches:
        return None
    return matches[0]


def _parse_import(format_name: str, body: bytes, source_uri: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    fmt = (format_name or "xccdf").lower()
    if fmt == "xccdf":
        return xccdf.parse_xccdf(body, source_uri=source_uri)
    if fmt == "cklb":
        return cklb.parse_cklb_baseline(body, source_uri=source_uri)
    if fmt == "ckl":
        return ckl.parse_ckl_baseline(body, source_uri=source_uri)
    raise ValueError(f"unsupported format: {format_name}")


def import_baseline(
    service,
    body: bytes,
    format_name: str,
    username: str,
    source_uri: str = "",
) -> Tuple[Dict[str, Any], bool]:
    meta, rules = _parse_import(format_name, body, source_uri)
    if not rules:
        raise ValueError("no rules parsed from import")

    content_fingerprint = baseline_content_fingerprint(meta, rules)
    existing = find_baseline_by_fingerprint(service, content_fingerprint)
    if existing:
        audit.log_event(
            "import_deduplicated",
            "stig_baseline",
            existing["_key"],
            username,
            {
                "format": format_name,
                "source_uri": source_uri or meta.get("source_uri"),
                "content_fingerprint": content_fingerprint,
            },
        )
        return existing, False

    baseline_coll = kv_client.get_collection(service, KV_STIG_BASELINES)
    rules_coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)

    ts = now_epoch()
    baseline_record = kv_record(
        {
            "stig_id": meta.get("stig_id"),
            "title": meta.get("title"),
            "stig_name": meta.get("stig_name"),
            "version": meta.get("version"),
            "release_info": meta.get("release_info"),
            "benchmark_date": meta.get("benchmark_date"),
            "xccdf_benchmark_id": meta.get("xccdf_benchmark_id"),
            "display_name": meta.get("display_name") or "",
            "reference_identifier": meta.get("reference_identifier") or "",
            "description": meta.get("description") or "",
            "classification": meta.get("classification") or "UNCLASSIFIED",
            "source_filename": meta.get("source_filename") or "",
            "notice": meta.get("notice") or "terms-of-use",
            "stig_source": meta.get("stig_source") or "STIG.DOD.MIL",
            "target_key": meta.get("target_key") or "",
            "uuid": meta.get("uuid") or "",
            "rule_count": len(rules),
            "source_type": meta.get("source_type"),
            "source_uri": source_uri or meta.get("source_uri"),
            "content_fingerprint": content_fingerprint,
            "imported_at": ts,
            "imported_by": username,
        }
    )
    stored_baseline = kv_client.insert_record(baseline_coll, baseline_record)
    baseline_id = stored_baseline["_key"]

    rule_records = []
    for rule in rules:
        rule_records.append(
            kv_record(
                {
                    "baseline_id": baseline_id,
                    "group_id": rule.get("group_id"),
                    "rule_id": rule.get("rule_id"),
                    "rule_id_src": rule.get("rule_id_src"),
                    "rule_version": rule.get("rule_version"),
                    "severity": rule.get("severity"),
                    "rule_title": rule.get("rule_title"),
                    "discussion": rule.get("discussion"),
                    "check_content": rule.get("check_content"),
                    "fix_text": rule.get("fix_text"),
                    "ccis": dumps_json(rule.get("ccis") or []),
                    "check_content_hash": rule.get("check_content_hash"),
                    "group_title": rule.get("group_title") or "",
                    "srg_id": rule.get("srg_id") or "",
                    "weight": rule.get("weight") or "10.0",
                    "check_content_ref": rule.get("check_content_ref") or "",
                    "reference_identifier": rule.get("reference_identifier")
                    or meta.get("reference_identifier")
                    or "",
                    "group_id_src": rule.get("group_id_src") or rule.get("group_id") or "",
                    "group_description": rule.get("group_description") or "",
                    "false_positives": rule.get("false_positives") or "",
                    "false_negatives": rule.get("false_negatives") or "",
                    "documentable": rule.get("documentable") or "false",
                    "mitigations": rule.get("mitigations") or "",
                    "security_override_guidance": rule.get("security_override_guidance")
                    or "",
                    "potential_impacts": rule.get("potential_impacts") or "",
                    "third_party_tools": rule.get("third_party_tools") or "",
                    "mitigation_control": rule.get("mitigation_control") or "",
                    "responsibility": rule.get("responsibility") or "",
                    "ia_controls": rule.get("ia_controls") or "",
                }
            )
        )
    kv_client.batch_insert(rules_coll, rule_records)

    audit.log_event(
        "import",
        "stig_baseline",
        baseline_id,
        username,
        {
            "rule_count": len(rules),
            "format": format_name,
            "content_fingerprint": content_fingerprint,
        },
    )
    return stored_baseline, True
