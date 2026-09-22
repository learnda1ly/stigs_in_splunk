"""STIG library browse: benchmark hierarchy and stable rule detail."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import kv_client
from models import KV_STIG_BASELINE_RULES
from services import baselines as baselines_svc
from services.revision_upgrade import parse_dis_version


def _benchmark_key(rec: Dict[str, Any]) -> str:
    sid = (rec.get("stig_id") or "").strip()
    if sid:
        return sid
    xccdf = (rec.get("xccdf_benchmark_id") or "").strip()
    if xccdf:
        if "_benchmark_" in xccdf:
            return xccdf.split("_benchmark_")[-1]
        return xccdf
    return (rec.get("_key") or "unknown").strip()


def _revision_sort_key(rec: Dict[str, Any]) -> Tuple[int, int, float, str]:
    ver = parse_dis_version(rec.get("version"))
    if ver:
        return (ver[0], ver[1], float(rec.get("imported_at") or 0), "")
    return (0, 0, float(rec.get("imported_at") or 0), str(rec.get("version") or ""))


def revision_summary(rec: Dict[str, Any]) -> Dict[str, Any]:
    rule_count = rec.get("rule_count")
    try:
        rule_count = int(rule_count) if rule_count is not None else 0
    except (TypeError, ValueError):
        rule_count = 0
    return {
        "baseline_id": rec.get("_key"),
        "stig_id": rec.get("stig_id") or "",
        "title": rec.get("title") or "",
        "stig_name": rec.get("stig_name") or "",
        "version": rec.get("version") or "",
        "release_info": rec.get("release_info") or "",
        "benchmark_date": rec.get("benchmark_date") or "",
        "content_fingerprint": rec.get("content_fingerprint") or "",
        "rule_count": rule_count,
        "imported_at": rec.get("imported_at"),
        "imported_by": rec.get("imported_by") or "",
        "xccdf_benchmark_id": rec.get("xccdf_benchmark_id") or "",
        "display_name": rec.get("display_name") or "",
        "ucc_name": rec.get("ucc_name") or "",
        "source_type": rec.get("source_type") or "",
        "source_uri": rec.get("source_uri") or "",
    }


def _benchmark_entry(stig_id: str, revisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    ordered = sorted(revisions, key=_revision_sort_key, reverse=True)
    latest = ordered[0]
    return {
        "stig_id": stig_id,
        "title": latest.get("title") or latest.get("stig_name") or stig_id,
        "stig_name": latest.get("stig_name") or "",
        "revision_count": len(ordered),
        "latest_baseline_id": latest.get("_key"),
        "latest_version": latest.get("version") or "",
        "revisions": [revision_summary(rec) for rec in ordered],
    }


def list_hierarchy(service) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for rec in baselines_svc.list_baselines(service):
        key = _benchmark_key(rec)
        grouped.setdefault(key, []).append(rec)
    benchmarks = [
        _benchmark_entry(stig_id, rows)
        for stig_id, rows in grouped.items()
    ]
    benchmarks.sort(key=lambda row: (row.get("stig_id") or "").casefold())
    total_baselines = sum(len(rows) for rows in grouped.values())
    return {
        "benchmark_count": len(benchmarks),
        "baseline_count": total_baselines,
        "benchmarks": benchmarks,
    }


def get_benchmark(service, stig_id: str) -> Optional[Dict[str, Any]]:
    want = (stig_id or "").strip().casefold()
    if not want:
        return None
    for entry in list_hierarchy(service)["benchmarks"]:
        if (entry.get("stig_id") or "").strip().casefold() == want:
            return entry
    return None


def rule_detail_payload(
    baseline: Dict[str, Any], rule: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "baseline_id": baseline.get("_key"),
        "stig_id": baseline.get("stig_id") or "",
        "baseline_version": baseline.get("version") or "",
        "baseline_title": baseline.get("title") or "",
        "rule": rule,
    }


def _rule_matches_ref(
    rule: Dict[str, Any], rule_ref: str, group_id: str = ""
) -> bool:
    ref = (rule_ref or "").strip()
    if not ref:
        return False
    gid_filter = (group_id or "").strip()
    if gid_filter and str(rule.get("group_id") or "").strip() != gid_filter:
        return False
    if ref == str(rule.get("_key") or "").strip():
        return True
    composite = "{}|{}".format(
        rule.get("group_id") or "", rule.get("rule_id") or ""
    )
    if ref == composite:
        return True
    for field in ("rule_id", "rule_id_src", "group_id"):
        if ref == str(rule.get(field) or "").strip():
            return True
    return False


def get_baseline_rule(
    service,
    baseline_id: str,
    rule_ref: str,
    group_id: str = "",
) -> Optional[Dict[str, Any]]:
    baseline = baselines_svc.get_baseline(service, baseline_id)
    if not baseline:
        return None
    ref = (rule_ref or "").strip()
    if not ref:
        return None
    rules_coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)
    by_key = kv_client.get_by_key(rules_coll, ref)
    if by_key and str(by_key.get("baseline_id") or "") == baseline_id:
        return rule_detail_payload(baseline, by_key)
    for rule in baselines_svc.list_baseline_rules(service, baseline_id):
        if _rule_matches_ref(rule, ref, group_id):
            return rule_detail_payload(baseline, rule)
    return None


def get_rule_by_key(service, rule_key: str) -> Optional[Dict[str, Any]]:
    key = (rule_key or "").strip()
    if not key:
        return None
    rules_coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)
    rule = kv_client.get_by_key(rules_coll, key)
    if not rule:
        return None
    baseline_id = str(rule.get("baseline_id") or "").strip()
    if not baseline_id:
        return None
    baseline = baselines_svc.get_baseline(service, baseline_id)
    if not baseline:
        return None
    return rule_detail_payload(baseline, rule)
