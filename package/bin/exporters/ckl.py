"""Build STIG Viewer–compatible CKL XML (Checklist Schema v2 / Viewer 2.18)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from cklb_shape import (
    check_content_ref,
    index_reviews,
    lookup_review,
    resolve_stig_id,
    srg_id,
    stable_uuid,
    viewer_rule,
    viewer_target_data,
)
from models import STATUS_TO_CKL, parse_json_field

VIEWER_COMMENT = "DISA STIG Viewer :: 2.18"
DEFAULT_DESCRIPTION = (
    "This Security Technical Implementation Guide is published as a tool to "
    "improve the security of Department of Defense (DOD) information systems. "
    "The requirements are derived from the National Institute of Standards and "
    "Technology (NIST) 800-53 and related documents. Comments or proposed "
    "revisions to this document should be sent via email to the following "
    "address: disa.stig_spt@mail.mil."
)
DEFAULT_CLASSIFICATION = "UNCLASSIFIED"
DEFAULT_NOTICE = "terms-of-use"
DEFAULT_SOURCE = "STIG.DOD.MIL"
DEFAULT_MARKING = "CUI"
DEFAULT_CLASS = "Unclass"

ASSET_TAGS = (
    "ROLE",
    "ASSET_TYPE",
    "MARKING",
    "HOST_NAME",
    "HOST_IP",
    "HOST_MAC",
    "HOST_FQDN",
    "TARGET_COMMENT",
    "TECH_AREA",
    "TARGET_KEY",
    "WEB_OR_DATABASE",
    "WEB_DB_SITE",
    "WEB_DB_INSTANCE",
)

STIG_INFO_NAMES = (
    "version",
    "classification",
    "customname",
    "stigid",
    "description",
    "filename",
    "releaseinfo",
    "title",
    "uuid",
    "notice",
    "source",
)

VULN_ATTR_ORDER = (
    "Vuln_Num",
    "Severity",
    "Group_Title",
    "Rule_ID",
    "Rule_Ver",
    "Rule_Title",
    "Vuln_Discuss",
    "IA_Controls",
    "Check_Content",
    "Fix_Text",
    "False_Positives",
    "False_Negatives",
    "Documentable",
    "Mitigations",
    "Potential_Impact",
    "Third_Party_Tools",
    "Mitigation_Control",
    "Responsibility",
    "Security_Override_Guidance",
    "Check_Content_Ref",
    "Weight",
    "Class",
    "STIGRef",
    "TargetKey",
    "STIG_UUID",
)

VULN_TRAILING = (
    "STATUS",
    "FINDING_DETAILS",
    "COMMENTS",
    "SEVERITY_OVERRIDE",
    "SEVERITY_JUSTIFICATION",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _bool_xml(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return "true"
        if lowered in ("false", "0", "no", ""):
            return "false"
    return "true" if value else "false"


def _ckl_class(value: Any) -> str:
    raw = _text(value).strip()
    if not raw or raw.lower() in ("unclassified", "unclass"):
        return DEFAULT_CLASS
    return raw


def _source_filename(baseline: Dict[str, Any]) -> str:
    explicit = _text(baseline.get("source_filename") or "").strip()
    if explicit:
        return explicit
    uri = _text(baseline.get("source_uri") or "").replace("\\", "/")
    name = os.path.basename(uri)
    return name if name.lower().endswith((".xml", ".ckl", ".cklb")) else name


def _stig_ref(baseline: Dict[str, Any]) -> str:
    title = _text(baseline.get("title") or baseline.get("stig_name") or "")
    version = _text(baseline.get("version") or "")
    release = _text(baseline.get("release_info") or "")
    if release:
        return f"{title} :: Version {version}, {release}"
    return f"{title} :: Version {version}"


def _legacy_ids(shaped: Dict[str, Any]) -> List[str]:
    raw = shaped.get("legacy_ids") or []
    if isinstance(raw, str):
        parsed = parse_json_field(raw, default=None)
        raw = parsed if isinstance(parsed, list) else [p for p in raw.split() if p]
    values = [_text(item) for item in raw]
    while len(values) < 2:
        values.append("")
    return values


def _ccis(shaped: Dict[str, Any]) -> List[str]:
    raw = shaped.get("ccis") or []
    if isinstance(raw, str):
        parsed = parse_json_field(raw, default=None)
        if isinstance(parsed, list):
            raw = parsed
        else:
            raw = [p for p in raw.replace(",", " ").split() if p]
    return [_text(item).strip() for item in raw if _text(item).strip()]


def _add(parent: ET.Element, tag: str, text: str = "") -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = _text(text)
    return node


def _si_data(parent: ET.Element, name: str, data: Optional[str]) -> None:
    si = ET.SubElement(parent, "SI_DATA")
    _add(si, "SID_NAME", name)
    if data is not None:
        _add(si, "SID_DATA", data)


def _stig_data(parent: ET.Element, attr: str, data: str = "") -> None:
    block = ET.SubElement(parent, "STIG_DATA")
    _add(block, "VULN_ATTRIBUTE", attr)
    _add(block, "ATTRIBUTE_DATA", data)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _write_xml(el: ET.Element, indent: int = 0) -> str:
    pad = "\t" * indent
    children = list(el)
    text = el.text if el.text is not None else ""
    if not children:
        return f"{pad}<{el.tag}>{_escape(text)}</{el.tag}>"
    lines = [f"{pad}<{el.tag}>"]
    for child in children:
        lines.append(_write_xml(child, indent + 1))
    lines.append(f"{pad}</{el.tag}>")
    return "\n".join(lines)


def dumps_ckl(root: ET.Element) -> str:
    body = _write_xml(root, 0)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<!--{VIEWER_COMMENT}-->\n"
        f"{body}\n"
    )


def export_ckl(
    checklist: Dict[str, Any],
    baseline: Dict[str, Any],
    rules: List[Dict[str, Any]],
    reviews_by_group: Any,
    host: Dict[str, Any],
) -> str:
    raw_target = parse_json_field(checklist.get("target_data"), default={}) or {}
    target = viewer_target_data(checklist, host)
    target_key = _text(
        raw_target.get("target_key")
        or raw_target.get("TARGET_KEY")
        or baseline.get("target_key")
        or ""
    )
    stig_id = resolve_stig_id(baseline)
    title = _text(baseline.get("title") or baseline.get("stig_name") or "")
    version = _text(baseline.get("version") or "")
    releaseinfo = _text(baseline.get("release_info") or "")
    stig_uuid = _text(baseline.get("uuid") or "") or stable_uuid(
        "stig", baseline.get("_key") or stig_id
    )
    istig_uuid = stable_uuid(
        "istig",
        checklist.get("_key") or checklist.get("id"),
        baseline.get("_key") or stig_id,
    )
    stigref = _stig_ref(baseline)

    checklist_el = ET.Element("CHECKLIST")
    asset = ET.SubElement(checklist_el, "ASSET")
    asset_values = {
        "ROLE": target.get("role") or "None",
        "ASSET_TYPE": target.get("target_type") or "Computing",
        "MARKING": raw_target.get("marking") or DEFAULT_MARKING,
        "HOST_NAME": target.get("host_name") or "",
        "HOST_IP": target.get("ip_address") or "",
        "HOST_MAC": target.get("mac_address") or "",
        "HOST_FQDN": target.get("fqdn") or "",
        "TARGET_COMMENT": target.get("comments") or "",
        "TECH_AREA": target.get("technology_area") or "",
        "TARGET_KEY": target_key,
        "WEB_OR_DATABASE": _bool_xml(target.get("is_web_database")),
        "WEB_DB_SITE": target.get("web_db_site") or "",
        "WEB_DB_INSTANCE": target.get("web_db_instance") or "",
    }
    for tag in ASSET_TAGS:
        _add(asset, tag, asset_values[tag])

    stigs = ET.SubElement(checklist_el, "STIGS")
    istig = ET.SubElement(stigs, "iSTIG")
    stig_info = ET.SubElement(istig, "STIG_INFO")
    info_values = {
        "version": version,
        "classification": _text(baseline.get("classification") or DEFAULT_CLASSIFICATION),
        "customname": _text(baseline.get("customname") or raw_target.get("customname") or ""),
        "stigid": stig_id,
        "description": _text(baseline.get("description") or DEFAULT_DESCRIPTION),
        "filename": _source_filename(baseline),
        "releaseinfo": releaseinfo,
        "title": title,
        "uuid": stig_uuid,
        "notice": _text(baseline.get("notice") or DEFAULT_NOTICE),
        "source": _text(baseline.get("stig_source") or DEFAULT_SOURCE),
    }
    for name in STIG_INFO_NAMES:
        value = info_values[name]
        if name == "customname" and not value:
            _si_data(stig_info, name, None)
        else:
            _si_data(stig_info, name, value)

    review_index = index_reviews(reviews_by_group)
    for rule in rules:
        review = lookup_review(rule, review_index)
        status = review.get("status") or "not_reviewed"
        shaped = viewer_rule(
            rule,
            review,
            baseline,
            istig_uuid,
            STATUS_TO_CKL.get(status, "Not_Reviewed"),
        )
        cref = shaped.get("check_content_ref") or check_content_ref(rule, baseline)
        attrs = {
            "Vuln_Num": shaped.get("group_id") or "",
            "Severity": shaped.get("severity") or "medium",
            "Group_Title": srg_id(rule) or shaped.get("srg_id") or "",
            "Rule_ID": shaped.get("rule_id_src") or "",
            "Rule_Ver": shaped.get("rule_version") or "",
            "Rule_Title": shaped.get("rule_title") or "",
            "Vuln_Discuss": shaped.get("discussion") or "",
            "IA_Controls": shaped.get("ia_controls") or "",
            "Check_Content": shaped.get("check_content") or "",
            "Fix_Text": shaped.get("fix_text") or "",
            "False_Positives": shaped.get("false_positives") or "",
            "False_Negatives": shaped.get("false_negatives") or "",
            "Documentable": shaped.get("documentable") or "false",
            "Mitigations": shaped.get("mitigations") or "",
            "Potential_Impact": shaped.get("potential_impacts") or "",
            "Third_Party_Tools": shaped.get("third_party_tools") or "",
            "Mitigation_Control": shaped.get("mitigation_control") or "",
            "Responsibility": shaped.get("responsibility") or "",
            "Security_Override_Guidance": shaped.get("security_override_guidance") or "",
            "Check_Content_Ref": (cref or {}).get("name") or "M",
            "Weight": shaped.get("weight") or "10.0",
            "Class": _ckl_class(shaped.get("classification")),
            "STIGRef": stigref,
            "TargetKey": target_key,
            "STIG_UUID": istig_uuid,
        }
        vuln = ET.SubElement(istig, "VULN")
        for attr in VULN_ATTR_ORDER:
            _stig_data(vuln, attr, _text(attrs[attr]))
        for legacy in _legacy_ids(shaped):
            _stig_data(vuln, "LEGACY_ID", legacy)
        for cci in _ccis(shaped):
            _stig_data(vuln, "CCI_REF", cci)
        trailing = {
            "STATUS": STATUS_TO_CKL.get(status, "Not_Reviewed"),
            "FINDING_DETAILS": review.get("finding_details") or "",
            "COMMENTS": review.get("comments") or "",
            "SEVERITY_OVERRIDE": review.get("severity_override") or "",
            "SEVERITY_JUSTIFICATION": review.get("severity_justification") or "",
        }
        for tag in VULN_TRAILING:
            _add(vuln, tag, trailing[tag])

    return dumps_ckl(checklist_el)
