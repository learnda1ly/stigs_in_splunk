"""Parse DISA-style XCCDF benchmark XML into baseline metadata and rules."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from cklb_shape import parse_disa_description
from models import check_content_hash, dumps_json, strip_ns


def _text(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _rule_idents(rule: ET.Element) -> Tuple[str, str, List[str], str]:
    group_id = ""
    rule_id = ""
    ccis: List[str] = []
    rule_version = ""
    for ident in rule.findall(".//{*}ident"):
        system = (ident.get("system") or "").lower()
        val = (ident.text or "").strip()
        if not val:
            continue
        if "cci" in system:
            ccis.append(val)
        elif val.startswith("V-"):
            group_id = val
        elif val.startswith("SV-"):
            rule_id = val
        elif not rule_version and "-" in val and not val.startswith("CCI"):
            rule_version = val
    version_el = rule.find("{*}version")
    if version_el is not None and version_el.text:
        rule_version = version_el.text.strip()
    return group_id, rule_id, ccis, rule_version


def _check_content(rule: ET.Element) -> str:
    parts: List[str] = []
    for check in rule.findall(".//{*}check"):
        for cc in check.findall(".//{*}check-content"):
            t = _text(cc)
            if t:
                parts.append(t)
    if parts:
        return "\n\n".join(parts)
    fix = rule.find("{*}check-content")
    return _text(fix)


def parse_xccdf(content: bytes | str, source_uri: str = "") -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    root = ET.fromstring(content)
    benchmark = root
    if strip_ns(root.tag) != "Benchmark":
        for el in root.iter():
            if strip_ns(el.tag) == "Benchmark":
                benchmark = el
                break

    title = _text(benchmark.find("{*}title"))
    benchmark_id = benchmark.get("id") or ""

    status_el = benchmark.find("{*}status")
    release_info = _text(status_el) if status_el is not None else ""
    benchmark_date = status_el.get("date", "") if status_el is not None else ""

    version_el = benchmark.find("{*}version")
    version = _text(version_el)

    if "_benchmark_" in benchmark_id:
        stig_id = benchmark_id.split("_benchmark_")[-1]
    else:
        stig_id = benchmark_id or "unknown_stig"
    for plain in benchmark.findall("{*}plain-text"):
        if plain.get("id") == "release-info":
            release_info = _text(plain) or release_info

    display = ""
    reference_identifier = ""
    for ref in benchmark.iter():
        if strip_ns(ref.tag) != "identifier" and strip_ns(ref.tag) != "subject":
            continue
        val = _text(ref)
        tag = strip_ns(ref.tag)
        if tag == "identifier" and val and not reference_identifier:
            reference_identifier = val
        if tag == "subject" and val and not display:
            display = val

    description = _text(benchmark.find("{*}description"))
    notice_el = benchmark.find("{*}notice")
    notice = ""
    if notice_el is not None:
        notice = (notice_el.get("id") or "").strip() or _text(notice_el)
    source_filename = ""
    if source_uri:
        source_filename = source_uri.replace("\\", "/").rsplit("/", 1)[-1]

    meta: Dict[str, Any] = {
        "stig_id": stig_id,
        "title": title or stig_id,
        "stig_name": title or stig_id,
        "display_name": display,
        "version": version,
        "release_info": release_info,
        "benchmark_date": benchmark_date,
        "xccdf_benchmark_id": benchmark_id,
        "source_type": "xccdf",
        "source_uri": source_uri,
        "source_filename": source_filename,
        "reference_identifier": reference_identifier,
        "description": description,
        "notice": notice or "terms-of-use",
        "classification": "UNCLASSIFIED",
        "stig_source": "STIG.DOD.MIL",
    }

    rules: List[Dict[str, Any]] = []
    group_title = ""
    group_id_from_group = ""
    group_description = ""
    for el in benchmark.iter():
        tag = strip_ns(el.tag)
        if tag == "Group":
            raw_gid = el.get("id") or ""
            group_id_from_group = (
                raw_gid.split("_group_")[-1] if "_group_" in raw_gid else raw_gid
            )
            group_title = _text(el.find("{*}title"))
            group_description = _text(el.find("{*}description"))
        elif tag == "Rule":
            ident_gid, ident_rid, ccis, rule_version = _rule_idents(el)
            group_id = ident_gid or group_id_from_group
            rule_id_src = el.get("id") or ""
            rule_id = ident_rid or rule_id_src
            if rule_id.endswith("_rule"):
                rule_id = rule_id[: -len("_rule")]
            check_text = _check_content(el)
            severity = (el.get("severity") or "medium").lower()
            parsed = parse_disa_description(_text(el.find("{*}description")))
            cref = el.find(".//{*}check-content-ref")
            check_ref = {}
            if cref is not None:
                check_ref = {
                    "href": cref.get("href") or "",
                    "name": cref.get("name") or "M",
                }
            srg = group_title if group_title.startswith("SRG-") else ""
            rules.append(
                {
                    "group_id": group_id,
                    "group_id_src": group_id,
                    "rule_id": rule_id,
                    "rule_id_src": rule_id_src,
                    "rule_version": rule_version,
                    "severity": severity,
                    "rule_title": _text(el.find("{*}title")),
                    "discussion": parsed.get("discussion") or _text(el.find("{*}description")),
                    "check_content": check_text,
                    "fix_text": _text(el.find("{*}fixtext")),
                    "ccis": ccis,
                    "check_content_hash": check_content_hash(check_text),
                    "group_title": group_title,
                    "group_description": group_description,
                    "srg_id": srg,
                    "weight": el.get("weight") or "10.0",
                    "check_content_ref": dumps_json(check_ref) if check_ref else "",
                    "reference_identifier": reference_identifier,
                    "false_positives": parsed.get("false_positives") or "",
                    "false_negatives": parsed.get("false_negatives") or "",
                    "documentable": parsed.get("documentable") or "false",
                    "mitigations": parsed.get("mitigations") or "",
                    "security_override_guidance": parsed.get("security_override_guidance")
                    or "",
                    "potential_impacts": parsed.get("potential_impacts") or "",
                    "third_party_tools": parsed.get("third_party_tools") or "",
                    "mitigation_control": parsed.get("mitigation_control") or "",
                    "responsibility": parsed.get("responsibility") or "",
                    "ia_controls": parsed.get("ia_controls") or "",
                }
            )

    meta["rule_count"] = len(rules)
    return meta, rules
