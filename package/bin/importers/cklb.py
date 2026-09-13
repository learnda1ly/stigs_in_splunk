"""Parse CKLB JSON for baseline import or checklist review updates."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

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
