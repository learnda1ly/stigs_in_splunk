"""STIG Viewer CKLB shaping helpers.

Used at export so already-imported baselines still emit Viewer-compatible files.
"""

from __future__ import annotations

import html
import re
import uuid
from typing import Any, Dict, List

from models import parse_json_field

CKLB_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://stigs_in_splunk/cklb")
_STIG_SUFFIX = " Security Technical Implementation Guide"
_SV_RE = re.compile(r"SV-(\d+)")

DESC_TAGS = (
    ("VulnDiscussion", "discussion"),
    ("FalsePositives", "false_positives"),
    ("FalseNegatives", "false_negatives"),
    ("Documentable", "documentable"),
    ("Mitigations", "mitigations"),
    ("SeverityOverrideGuidance", "security_override_guidance"),
    ("PotentialImpacts", "potential_impacts"),
    ("ThirdPartyTools", "third_party_tools"),
    ("MitigationControl", "mitigation_control"),
    ("Responsibility", "responsibility"),
    ("IAControls", "ia_controls"),
)


def stable_uuid(*parts: Any) -> str:
    return str(uuid.uuid5(CKLB_NS, "|".join(str(p or "") for p in parts)))


def strip_rule_suffix(rule_id: str) -> str:
    rid = (rule_id or "").strip()
    if rid.endswith("_rule"):
        return rid[: -len("_rule")]
    return rid


def viewer_rule_ids(rule: Dict[str, Any]) -> tuple[str, str]:
    src = (rule.get("rule_id_src") or rule.get("rule_id") or "").strip()
    rid = (rule.get("rule_id") or src).strip()
    if not src.endswith("_rule") and rid.endswith("_rule"):
        src = rid
    if src.endswith("_rule"):
        rid = src[: -len("_rule")]
    elif rid.endswith("_rule"):
        rid = rid[: -len("_rule")]
    return src or rid, rid


def derive_group_id(rule: Dict[str, Any]) -> str:
    gid = (rule.get("group_id") or "").strip()
    if gid:
        if "_group_" in gid:
            gid = gid.split("_group_")[-1]
        return gid
    src, rid = viewer_rule_ids(rule)
    match = _SV_RE.match(src or rid)
    if match:
        return f"V-{match.group(1)}"
    return ""


def parse_disa_description(raw: Any) -> Dict[str, str]:
    empty = {dest: "" for _src, dest in DESC_TAGS}
    empty["documentable"] = "false"
    text = str(raw or "")
    if not text:
        return dict(empty)
    if "&lt;VulnDiscussion" in text and "<VulnDiscussion>" not in text:
        text = html.unescape(text)
    if "<VulnDiscussion>" not in text:
        empty["discussion"] = text
        return empty
    out = dict(empty)
    for tag, dest in DESC_TAGS:
        match = re.search(rf"<{tag}>(.*?)</{tag}>", text, flags=re.DOTALL)
        if match:
            out[dest] = match.group(1)
    if not out["documentable"]:
        out["documentable"] = "false"
    return out


def resolve_stig_id(baseline: Dict[str, Any]) -> str:
    xid = (baseline.get("xccdf_benchmark_id") or "").strip()
    if "_benchmark_" in xid:
        return xid.split("_benchmark_")[-1]
    if xid:
        return xid
    sid = (baseline.get("stig_id") or "").strip()
    if sid and sid != "STIG":
        return sid
    return sid or "unknown_stig"


def display_name(baseline: Dict[str, Any]) -> str:
    explicit = (baseline.get("display_name") or "").strip()
    if explicit:
        return explicit
    title = (baseline.get("stig_name") or baseline.get("title") or "").strip()
    if title.endswith(_STIG_SUFFIX):
        return title[: -len(_STIG_SUFFIX)]
    return title


def check_content_ref(rule: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, str]:
    stored = parse_json_field(rule.get("check_content_ref"), default=None)
    if isinstance(stored, dict) and stored.get("href"):
        return {"href": str(stored.get("href")), "name": str(stored.get("name") or "M")}
    name = display_name(baseline) or "STIG"
    href = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + "_STIG.xml"
    return {"href": href, "name": "M"}


def srg_id(rule: Dict[str, Any]) -> str:
    explicit = (rule.get("srg_id") or "").strip()
    if explicit:
        return explicit
    title = (rule.get("group_title") or "").strip()
    if title.startswith("SRG-"):
        return title
    return ""


def index_reviews(reviews: Any) -> Dict[str, Dict[str, Any]]:
    """Map group_id / rule_id / rule_version → review."""
    out: Dict[str, Dict[str, Any]] = {}
    rows: List[Dict[str, Any]]
    if isinstance(reviews, dict):
        rows = [v for v in reviews.values() if isinstance(v, dict)]
        for key, rec in reviews.items():
            if isinstance(rec, dict) and key:
                out[str(key)] = rec
    else:
        rows = list(reviews or [])
    for rec in rows:
        for key in (
            rec.get("group_id"),
            rec.get("rule_id"),
            rec.get("rule_version"),
            strip_rule_suffix(rec.get("rule_id") or ""),
        ):
            if key:
                out.setdefault(str(key), rec)
    return out


def lookup_review(rule: Dict[str, Any], index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    src, rid = viewer_rule_ids(rule)
    gid = derive_group_id(rule)
    for key in (gid, rid, src, rule.get("rule_id"), rule.get("rule_version"), rule.get("group_id")):
        if key and key in index:
            return index[key]
    return {}


def viewer_target_data(checklist: Dict[str, Any], host: Dict[str, Any]) -> Dict[str, Any]:
    raw = parse_json_field(checklist.get("target_data"), default={}) or {}
    asset = raw.get("target_type") or raw.get("asset_type") or host.get("asset_type") or "Computing"
    web = raw.get("is_web_database")
    if web is None:
        web = bool(host.get("web_or_database"))
    return {
        "target_type": asset,
        "host_name": raw.get("host_name") or host.get("hostname") or "",
        "ip_address": raw.get("ip_address") or host.get("ip_address") or "",
        "mac_address": raw.get("mac_address") or host.get("mac_address") or "",
        "fqdn": raw.get("fqdn") or host.get("fqdn") or "",
        "comments": raw.get("comments") or "",
        "role": raw.get("role") or host.get("role") or "None",
        "is_web_database": bool(web),
        "technology_area": raw.get("technology_area") or host.get("tech_area") or "",
        "web_db_site": raw.get("web_db_site") or "",
        "web_db_instance": raw.get("web_db_instance") or "",
        "classification": raw.get("classification", None),
    }


def viewer_rule(
    rule: Dict[str, Any],
    review: Dict[str, Any],
    baseline: Dict[str, Any],
    stig_uuid: str,
    status: str,
) -> Dict[str, Any]:
    src, rid = viewer_rule_ids(rule)
    gid = derive_group_id(rule)
    parsed = parse_disa_description(rule.get("discussion"))
    srg = srg_id(rule)
    title = rule.get("rule_title") or ""
    ref_id = (
        rule.get("reference_identifier")
        or baseline.get("reference_identifier")
        or ""
    )
    extras = {
        "false_positives": rule.get("false_positives"),
        "false_negatives": rule.get("false_negatives"),
        "documentable": rule.get("documentable"),
        "mitigations": rule.get("mitigations"),
        "security_override_guidance": rule.get("security_override_guidance"),
        "potential_impacts": rule.get("potential_impacts"),
        "third_party_tools": rule.get("third_party_tools"),
        "mitigation_control": rule.get("mitigation_control"),
        "responsibility": rule.get("responsibility"),
        "ia_controls": rule.get("ia_controls"),
    }
    for key, val in extras.items():
        if val not in (None, ""):
            parsed[key] = str(val)

    return {
        "group_id_src": gid,
        "group_tree": [
            {
                "id": gid,
                "title": srg,
                "description": rule.get("group_description")
                or "<GroupDescription></GroupDescription>",
            }
        ],
        "group_id": gid,
        "severity": rule.get("severity") or "medium",
        "group_title": title,
        "rule_id_src": src,
        "rule_id": rid,
        "rule_version": rule.get("rule_version") or "",
        "rule_title": title,
        "fix_text": rule.get("fix_text") or "",
        "weight": str(rule.get("weight") or "10.0"),
        "check_content": rule.get("check_content") or "",
        "check_content_ref": check_content_ref(rule, baseline),
        "classification": rule.get("classification") or "Unclassified",
        "discussion": parsed.get("discussion") or "",
        "false_positives": parsed.get("false_positives") or "",
        "false_negatives": parsed.get("false_negatives") or "",
        "documentable": parsed.get("documentable") or "false",
        "security_override_guidance": parsed.get("security_override_guidance") or "",
        "potential_impacts": parsed.get("potential_impacts") or "",
        "third_party_tools": parsed.get("third_party_tools") or "",
        "ia_controls": parsed.get("ia_controls") or "",
        "responsibility": parsed.get("responsibility") or "",
        "mitigations": parsed.get("mitigations") or "",
        "mitigation_control": parsed.get("mitigation_control") or "",
        "legacy_ids": parse_json_field(rule.get("legacy_ids"), default=[]) or [],
        "ccis": parse_json_field(rule.get("ccis"), default=[]) or [],
        "reference_identifier": str(ref_id),
        "uuid": rule.get("uuid") or stable_uuid("rule", baseline.get("_key"), rid or rule.get("rule_version")),
        "stig_uuid": stig_uuid,
        "status": status,
        "overrides": {},
        "comments": review.get("comments") or "",
        "finding_details": review.get("finding_details") or "",
        "srg_id": srg,
        "package_id": review.get("package_id") or "",
    }
