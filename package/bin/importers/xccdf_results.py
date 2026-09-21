"""Parse XCCDF TestResult (scan) XML into Watcher-shaped checklist ingest."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from importers.ingest import empty_stats, revision_str, streamed_review, tally_result
from models import strip_ns

XCCDF_RESULT_TO_WATCHER = {
    "pass": "pass",
    "fail": "fail",
    "notapplicable": "notapplicable",
    "notchecked": "notchecked",
    "notselected": "notchecked",
    "unknown": "notchecked",
    "error": "notchecked",
    "informational": "notchecked",
    "fixed": "pass",
}


def _text(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _stig_id_from_benchmark_ref(href: str, benchmark_id: str = "") -> str:
    bid = (benchmark_id or href or "").strip()
    if not bid:
        return ""
    bid = bid.lstrip("#")
    if "_benchmark_" in bid:
        return bid.split("_benchmark_")[-1]
    return bid


def _rule_ids_from_idref(idref: str) -> Tuple[str, str]:
    raw = (idref or "").strip()
    if not raw:
        return "", ""
    rule_id = raw
    if "_rule_" in raw:
        rule_id = raw.split("_rule_")[-1]
    elif raw.endswith("_rule"):
        rule_id = raw[: -len("_rule")]
    group_id = ""
    if rule_id.startswith("SV-"):
        base = rule_id[3:].split("r")[0].split("R")[0]
        if base:
            group_id = "V-" + base
    return rule_id, group_id


def _find_test_results(root: ET.Element) -> List[ET.Element]:
    if strip_ns(root.tag) == "TestResult":
        return [root]
    found: List[ET.Element] = []
    for el in root.iter():
        if strip_ns(el.tag) == "TestResult":
            found.append(el)
    return found


def _benchmark_meta_from_doc(root: ET.Element, benchmark_href: str) -> Dict[str, Any]:
    benchmark_el = None
    href_key = benchmark_href.lstrip("#")
    for el in root.iter():
        if strip_ns(el.tag) != "Benchmark":
            continue
        bid = el.get("id") or ""
        if href_key and bid and bid != href_key:
            continue
        benchmark_el = el
        break
    stig_id = ""
    title = ""
    version = ""
    release_info = ""
    xccdf_benchmark_id = ""
    if benchmark_el is not None:
        xccdf_benchmark_id = benchmark_el.get("id") or ""
        title = _text(benchmark_el.find("{*}title"))
        version = _text(benchmark_el.find("{*}version"))
        status_el = benchmark_el.find("{*}status")
        release_info = _text(status_el) if status_el is not None else ""
        for plain in benchmark_el.findall("{*}plain-text"):
            if plain.get("id") == "release-info":
                release_info = _text(plain) or release_info
    if not stig_id:
        stig_id = _stig_id_from_benchmark_ref(benchmark_href, xccdf_benchmark_id)
    return {
        "stig_id": stig_id or "unknown_stig",
        "title": title or stig_id,
        "stig_name": title or stig_id,
        "version": version,
        "release_info": release_info,
        "xccdf_benchmark_id": xccdf_benchmark_id,
        "source_type": "xccdf-results",
    }


def parse_xccdf_results(
    content: bytes | str, source_uri: str = ""
) -> Dict[str, Any]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    root = ET.fromstring(content)
    test_results = _find_test_results(root)
    if not test_results:
        raise ValueError("no XCCDF TestResult element found")

    checklists: List[Dict[str, Any]] = []
    errors: List[str] = []
    target_name = ""
    target_ip = ""

    for tr in test_results:
        hostname = _text(tr.find("{*}target"))
        if not hostname:
            hostname = _text(tr.find("{*}target-address"))
        if hostname and not target_name:
            target_name = hostname

        benchmark_el = tr.find("{*}benchmark")
        benchmark_href = benchmark_el.get("href", "") if benchmark_el is not None else ""
        meta = _benchmark_meta_from_doc(root, benchmark_href)
        if not meta.get("stig_id") or meta.get("stig_id") == "unknown_stig":
            meta["stig_id"] = _stig_id_from_benchmark_ref(
                benchmark_href, meta.get("xccdf_benchmark_id") or ""
            )
        benchmark_id = meta.get("stig_id") or ""

        stats = empty_stats()
        reviews: List[Dict[str, Any]] = []
        engine_product = (tr.get("test-system") or "").strip() or "xccdf-scan"
        result_engine = {"product": engine_product, "source": source_uri or ""}

        for rr in tr.iter():
            if strip_ns(rr.tag) != "rule-result":
                continue
            idref = rr.get("idref") or ""
            raw_result = (rr.get("result") or "notchecked").strip().lower()
            watcher_result = XCCDF_RESULT_TO_WATCHER.get(raw_result, "notchecked")
            tally_result(stats, watcher_result)
            rule_id, group_id = _rule_ids_from_idref(idref)
            if not rule_id and idref:
                rule_id = idref
            detail_parts: List[str] = []
            for msg in rr.findall("{*}message"):
                t = _text(msg)
                if t:
                    detail_parts.append(t)
            check_el = rr.find("{*}check")
            if check_el is not None:
                for cc in check_el.findall(".//{*}check-content"):
                    t = _text(cc)
                    if t:
                        detail_parts.append(t)
            review = streamed_review(
                rule_id=rule_id or idref,
                group_id=group_id,
                result=watcher_result,
                detail="\n".join(detail_parts),
                comment="",
                result_engine=result_engine,
            )
            reviews.append(review)

        if not reviews:
            errors.append("TestResult has no rule-result entries")
            continue

        checklists.append(
            {
                "benchmarkId": benchmark_id,
                "revisionStr": revision_str(meta.get("version"), meta.get("release_info")),
                "baseline_meta": meta,
                "baseline_rules": [],
                "reviews": reviews,
                "stats": stats,
                "sourceRef": source_uri or "",
            }
        )

    if not target_name and checklists:
        target_name = "unknown-host"

    return {
        "target": {
            "name": target_name,
            "ip": target_ip,
            "noncomputing": False,
            "description": "",
            "metadata": {},
        },
        "target_data": {
            "host_name": target_name,
            "ip_address": target_ip,
        },
        "checklists": checklists,
        "errors": errors,
    }
