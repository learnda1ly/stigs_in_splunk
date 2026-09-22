"""Build OpenSCAP / Evaluate-STIG–shaped XCCDF TestResult XML from KV reviews.

Results-only export: not a SCAP data stream or Manual STIG benchmark bundle.
Baseline rules without a resolvable XCCDF rule idref are skipped (no rule-result),
unlike CKL/CKLB export which still emits those rule rows.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from cklb_shape import index_reviews, lookup_review, resolve_stig_id, viewer_rule_ids
from models import STATUS_TO_RESULT

XCCDF_NS = "http://checklists.nist.gov/xccdf/1.2"
EXPORT_TEST_SYSTEM = "stigs_in_splunk:collection-archive-export"


def _benchmark_element_id(baseline: Dict[str, Any]) -> str:
    bid = (baseline.get("xccdf_benchmark_id") or "").strip()
    if bid:
        return bid.lstrip("#")
    stig_id = resolve_stig_id(baseline)
    return f"xccdf_mil.disa.stig_benchmark_{stig_id}"


def _rule_idref(rule: Dict[str, Any]) -> str:
    src, rid = viewer_rule_ids(rule)
    raw = (src or rid or rule.get("group_id") or "").strip()
    if not raw:
        return ""
    if raw.startswith("xccdf_"):
        return raw
    if raw.startswith("SV-") or raw.startswith("V-"):
        return f"xccdf_mil.disa.stig_rule_{rid or raw}"
    return raw


def _iso_timestamp(epoch: Any) -> str:
    try:
        when = datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc)
    except (TypeError, ValueError, OSError):
        when = datetime.datetime.now(datetime.timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%S")


def export_xccdf_results(
    checklist: Dict[str, Any],
    baseline: Dict[str, Any],
    rules: List[Dict[str, Any]],
    reviews: Any,
    host: Dict[str, Any],
) -> str:
    """Serialize one checklist as XCCDF 1.2 TestResult (results only, not full SCAP bundle)."""
    review_index = index_reviews(reviews)
    benchmark_id = _benchmark_element_id(baseline)
    hostname = (host.get("hostname") or checklist.get("title") or "unknown-host").strip()
    updated = checklist.get("updated_at") or checklist.get("created_at")

    ET.register_namespace("", XCCDF_NS)
    root = ET.Element(
        f"{{{XCCDF_NS}}}TestResult",
        {
            "id": f"xccdf_org.stigs_in_splunk.test_result_{checklist.get('_key') or 'export'}",
            "test-system": EXPORT_TEST_SYSTEM,
            "start-time": _iso_timestamp(updated),
            "end-time": _iso_timestamp(updated),
        },
    )

    bench = ET.SubElement(root, f"{{{XCCDF_NS}}}benchmark", {"href": f"#{benchmark_id}"})
    bench.text = ""

    target = ET.SubElement(root, f"{{{XCCDF_NS}}}target")
    target.text = hostname

    for rule in rules:
        review = lookup_review(rule, review_index)
        status = (review.get("status") or "not_reviewed").strip()
        result = STATUS_TO_RESULT.get(status, "notchecked")
        idref = _rule_idref(rule)
        if not idref:
            continue
        rr = ET.SubElement(
            root,
            f"{{{XCCDF_NS}}}rule-result",
            {"idref": idref, "result": result},
        )
        detail = (review.get("finding_details") or "").strip()
        if detail:
            msg = ET.SubElement(rr, f"{{{XCCDF_NS}}}message", {"severity": "info"})
            msg.text = detail

    xml_body = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if not xml_body.startswith("<?xml"):
        xml_body = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
    return xml_body
