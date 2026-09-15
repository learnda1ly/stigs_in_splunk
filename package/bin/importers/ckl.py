"""Parse CKL XML for baseline import and Watcher-shaped checklist ingest."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from importers import ingest as ingest_lib
from models import check_content_hash, strip_ns


def _vuln_map(vuln: ET.Element) -> Tuple[Dict[str, str], List[str], List[str]]:
    data: Dict[str, str] = {}
    ccis: List[str] = []
    legacy: List[str] = []
    for stig_data in vuln.findall(".//STIG_DATA"):
        attr_el = stig_data.find("VULN_ATTRIBUTE")
        val_el = stig_data.find("ATTRIBUTE_DATA")
        if attr_el is None:
            continue
        key = (attr_el.text or "").strip()
        val = (val_el.text or "").strip() if val_el is not None else ""
        if not key:
            continue
        if key in ("CCI", "CCI_REF", "CCIs"):
            if val:
                ccis.append(val)
            continue
        if key == "LEGACY_ID":
            if val:
                legacy.append(val)
            continue
        data[key] = val
    return data, ccis, legacy


def parse_ckl_baseline(content: bytes | str, source_uri: str = "") -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    root = ET.fromstring(content)

    stig_info: Dict[str, str] = {}
    for si in root.findall(".//STIG_INFO"):
        for sdata in si.findall("SI_DATA"):
            name = sdata.find("SID_NAME")
            val = sdata.find("SID_DATA")
            if name is not None and name.text:
                stig_info[name.text.strip()] = (val.text or "").strip() if val is not None else ""

    asset = root.find("ASSET")
    target_key = ""
    if asset is not None:
        target_key = (asset.findtext("TARGET_KEY") or "").strip()

    title = stig_info.get("title") or stig_info.get("Title") or "Imported CKL"
    filename = stig_info.get("filename") or ""
    if not filename and source_uri:
        filename = os.path.basename(source_uri.replace("\\", "/"))
    meta: Dict[str, Any] = {
        "stig_id": stig_info.get("stigid")
        or stig_info.get("stig_id")
        or stig_info.get("StigId")
        or "unknown_stig",
        "title": title,
        "stig_name": title,
        "version": stig_info.get("version") or "",
        "release_info": stig_info.get("releaseinfo") or stig_info.get("ReleaseInfo") or "",
        "benchmark_date": stig_info.get("benchmark_date") or "",
        "xccdf_benchmark_id": "",
        "source_type": "ckl",
        "source_uri": source_uri,
        "source_filename": filename,
        "description": stig_info.get("description") or "",
        "classification": stig_info.get("classification") or "UNCLASSIFIED",
        "notice": stig_info.get("notice") or "terms-of-use",
        "stig_source": stig_info.get("source") or "STIG.DOD.MIL",
        "target_key": target_key,
        "uuid": stig_info.get("uuid") or "",
    }

    rules: List[Dict[str, Any]] = []
    for vuln in root.findall(".//VULN"):
        attrs, ccis, legacy = _vuln_map(vuln)
        check_text = attrs.get("Check_Content") or attrs.get("Check_Text") or ""
        group_title = attrs.get("Group_Title") or ""
        rules.append(
            {
                "group_id": attrs.get("Vuln_Num") or attrs.get("Group_ID") or "",
                "rule_id": attrs.get("Rule_ID") or attrs.get("RuleID") or "",
                "rule_id_src": attrs.get("Rule_ID") or "",
                "rule_version": attrs.get("Rule_Ver") or attrs.get("RuleVersion") or "",
                "severity": (attrs.get("Severity") or "medium").lower(),
                "rule_title": attrs.get("Rule_Title") or attrs.get("RuleTitle") or "",
                "discussion": attrs.get("Vuln_Discuss") or attrs.get("VulnDiscussion") or "",
                "check_content": check_text,
                "fix_text": attrs.get("Fix_Text") or attrs.get("FixText") or "",
                "ccis": ccis,
                "legacy_ids": legacy,
                "check_content_hash": check_content_hash(check_text),
                "group_title": group_title,
                "srg_id": group_title if group_title.startswith("SRG-") else "",
                "weight": attrs.get("Weight") or "10.0",
                "ia_controls": attrs.get("IA_Controls") or "",
                "false_positives": attrs.get("False_Positives") or "",
                "false_negatives": attrs.get("False_Negatives") or "",
                "documentable": attrs.get("Documentable") or "false",
                "mitigations": attrs.get("Mitigations") or "",
                "potential_impacts": attrs.get("Potential_Impact") or "",
                "third_party_tools": attrs.get("Third_Party_Tools") or "",
                "mitigation_control": attrs.get("Mitigation_Control") or "",
                "responsibility": attrs.get("Responsibility") or "",
                "security_override_guidance": attrs.get("Security_Override_Guidance") or "",
            }
        )

    meta["rule_count"] = len(rules)
    return meta, rules


def _text(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    return (element.text or "").strip()


def _child_text(parent: Optional[ET.Element], tag: str) -> str:
    if parent is None:
        return ""
    return _text(parent.find(tag))


def _stig_info_map(container: ET.Element) -> Dict[str, str]:
    info: Dict[str, str] = {}
    for si in container.findall("STIG_INFO"):
        for sdata in si.findall("SI_DATA"):
            name = sdata.find("SID_NAME")
            val = sdata.find("SID_DATA")
            if name is not None and name.text:
                info[name.text.strip()] = (val.text or "").strip() if val is not None else ""
    if info:
        return info
    for si in container.findall(".//STIG_INFO"):
        for sdata in si.findall("SI_DATA"):
            name = sdata.find("SID_NAME")
            val = sdata.find("SID_DATA")
            if name is not None and name.text:
                info[name.text.strip()] = (val.text or "").strip() if val is not None else ""
    return info


def _istig_elements(root: ET.Element) -> List[ET.Element]:
    istigs = root.findall(".//iSTIG")
    if istigs:
        return istigs
    return [root]


def _rules_from_vulns(vulns: List[ET.Element]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for vuln in vulns:
        attrs, ccis, legacy = _vuln_map(vuln)
        check_text = attrs.get("Check_Content") or attrs.get("Check_Text") or ""
        group_title = attrs.get("Group_Title") or ""
        rules.append(
            {
                "group_id": attrs.get("Vuln_Num") or attrs.get("Group_ID") or "",
                "rule_id": attrs.get("Rule_ID") or attrs.get("RuleID") or "",
                "rule_id_src": attrs.get("Rule_ID") or "",
                "rule_version": attrs.get("Rule_Ver") or attrs.get("RuleVersion") or "",
                "severity": (attrs.get("Severity") or "medium").lower(),
                "rule_title": attrs.get("Rule_Title") or attrs.get("RuleTitle") or "",
                "discussion": attrs.get("Vuln_Discuss") or attrs.get("VulnDiscussion") or "",
                "check_content": check_text,
                "fix_text": attrs.get("Fix_Text") or attrs.get("FixText") or "",
                "ccis": ccis,
                "legacy_ids": legacy,
                "check_content_hash": check_content_hash(check_text),
                "group_title": group_title,
                "srg_id": group_title if group_title.startswith("SRG-") else "",
                "weight": attrs.get("Weight") or "10.0",
                "ia_controls": attrs.get("IA_Controls") or "",
                "false_positives": attrs.get("False_Positives") or "",
                "false_negatives": attrs.get("False_Negatives") or "",
                "documentable": attrs.get("Documentable") or "false",
                "mitigations": attrs.get("Mitigations") or "",
                "potential_impacts": attrs.get("Potential_Impact") or "",
                "third_party_tools": attrs.get("Third_Party_Tools") or "",
                "mitigation_control": attrs.get("Mitigation_Control") or "",
                "responsibility": attrs.get("Responsibility") or "",
                "security_override_guidance": attrs.get("Security_Override_Guidance") or "",
            }
        )
    return rules


def _baseline_from_info(
    stig_info: Dict[str, str],
    rules: List[Dict[str, Any]],
    source_uri: str,
    target_key: str = "",
) -> Dict[str, Any]:
    title = stig_info.get("title") or stig_info.get("Title") or "Imported CKL"
    filename = stig_info.get("filename") or ""
    if not filename and source_uri:
        filename = os.path.basename(source_uri.replace("\\", "/"))
    return {
        "stig_id": stig_info.get("stigid")
        or stig_info.get("stig_id")
        or stig_info.get("StigId")
        or "unknown_stig",
        "title": title,
        "stig_name": title,
        "version": stig_info.get("version") or "",
        "release_info": stig_info.get("releaseinfo") or stig_info.get("ReleaseInfo") or "",
        "benchmark_date": stig_info.get("benchmark_date") or "",
        "xccdf_benchmark_id": "",
        "source_type": "ckl",
        "source_uri": source_uri,
        "source_filename": filename,
        "description": stig_info.get("description") or "",
        "classification": stig_info.get("classification") or "UNCLASSIFIED",
        "notice": stig_info.get("notice") or "terms-of-use",
        "stig_source": stig_info.get("source") or "STIG.DOD.MIL",
        "target_key": target_key,
        "uuid": stig_info.get("uuid") or "",
        "rule_count": len(rules),
    }


def parse_ckl_asset(root: ET.Element) -> Dict[str, Any]:
    asset = root.find("ASSET")
    if asset is None:
        asset = root.find(".//ASSET")
    host_name = _child_text(asset, "HOST_NAME")
    metadata: Dict[str, Any] = {}
    role = _child_text(asset, "ROLE")
    if role:
        metadata["cklRole"] = role
    tech = _child_text(asset, "TECH_AREA")
    if tech:
        metadata["cklTechArea"] = tech
    web_or_db = _child_text(asset, "WEB_OR_DATABASE").lower() == "true"
    if web_or_db:
        metadata["cklWebOrDatabase"] = "true"
        metadata["cklHostName"] = host_name
        site = _child_text(asset, "WEB_DB_SITE")
        if site:
            metadata["cklWebDbSite"] = site
        instance = _child_text(asset, "WEB_DB_INSTANCE")
        if instance:
            metadata["cklWebDbInstance"] = instance
    ip = ingest_lib.truncate(_child_text(asset, "HOST_IP"), ingest_lib.MAX_NAME_LENGTH)
    fqdn = ingest_lib.truncate(_child_text(asset, "HOST_FQDN"), ingest_lib.MAX_NAME_LENGTH)
    mac = ingest_lib.truncate(_child_text(asset, "HOST_MAC"), ingest_lib.MAX_NAME_LENGTH)
    return {
        "name": ingest_lib.truncate(host_name, ingest_lib.MAX_NAME_LENGTH) or "",
        "description": ingest_lib.truncate(
            _child_text(asset, "TARGET_COMMENT"), ingest_lib.MAX_NAME_LENGTH
        ),
        "ip": ip or None,
        "fqdn": fqdn or None,
        "mac": mac or None,
        "noncomputing": _child_text(asset, "ASSET_TYPE") == "Non-Computing",
        "metadata": metadata,
        "role": role or "None",
        "asset_type": _child_text(asset, "ASSET_TYPE") or "Computing",
        "tech_area": tech,
        "web_or_database": web_or_db,
        "web_db_site": _child_text(asset, "WEB_DB_SITE"),
        "web_db_instance": _child_text(asset, "WEB_DB_INSTANCE"),
        "target_key": _child_text(asset, "TARGET_KEY"),
        "marking": _child_text(asset, "MARKING"),
    }


def _target_data_from_asset(target: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "target_type": "Non-Computing" if target.get("noncomputing") else (
            target.get("asset_type") or "Computing"
        ),
        "host_name": target.get("name") or "",
        "ip_address": target.get("ip") or "",
        "mac_address": target.get("mac") or "",
        "fqdn": target.get("fqdn") or "",
        "comments": target.get("description") or "",
        "role": target.get("role") or "None",
        "is_web_database": bool(target.get("web_or_database")),
        "technology_area": target.get("tech_area") or "",
        "web_db_site": target.get("web_db_site") or "",
        "web_db_instance": target.get("web_db_instance") or "",
        "target_key": target.get("target_key") or "",
    }


def _reviews_from_vulns(vulns: List[ET.Element]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    reviews: List[Dict[str, Any]] = []
    stats = ingest_lib.empty_stats()
    for vuln in vulns:
        attrs, _ccis, _legacy = _vuln_map(vuln)
        rule_id = attrs.get("Rule_ID") or attrs.get("RuleID") or ""
        result = ingest_lib.result_from_status(_child_text(vuln, "STATUS"), source="ckl")
        if not result and not rule_id:
            continue
        if not result:
            result = "notchecked"
        if not rule_id:
            continue
        review = ingest_lib.streamed_review(
            rule_id=rule_id,
            result=result,
            detail=_child_text(vuln, "FINDING_DETAILS"),
            comment=_child_text(vuln, "COMMENTS"),
            status="saved",
            group_id=attrs.get("Vuln_Num") or attrs.get("Group_ID") or "",
        )
        reviews.append(review)
        ingest_lib.tally_result(stats, review.get("result"))
    return reviews, stats


def parse_ckl_ingest(content: bytes | str, source_uri: str = "") -> Dict[str, Any]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    root = ET.fromstring(content)
    if strip_ns(root.tag) != "CHECKLIST":
        found = None
        for el in root.iter():
            if strip_ns(el.tag) == "CHECKLIST":
                found = el
                break
        if found is None:
            raise ValueError("No CHECKLIST element")
        root = found

    target = parse_ckl_asset(root)
    if not target.get("name"):
        raise ValueError("No host_name in ASSET")
    if len(target["name"]) > ingest_lib.MAX_NAME_LENGTH:
        raise ValueError("Asset hostname cannot be more than 255 characters")

    target_data = _target_data_from_asset(target)
    checklists: List[Dict[str, Any]] = []
    errors: List[str] = []
    for istig in _istig_elements(root):
        stig_info = _stig_info_map(istig)
        stig_id = (
            stig_info.get("stigid")
            or stig_info.get("stig_id")
            or stig_info.get("StigId")
            or ""
        )
        stig_id = stig_id.replace("xccdf_mil.disa.stig_benchmark_", "")
        if not stig_id:
            errors.append("STIG_INFO element has no SI_DATA for SID_NAME == stigid")
            continue
        vulns = list(istig.findall("VULN")) or list(istig.findall(".//VULN"))
        rules = _rules_from_vulns(vulns)
        reviews, stats = _reviews_from_vulns(vulns)
        meta = _baseline_from_info(stig_info, rules, source_uri, target.get("target_key") or "")
        meta["stig_id"] = stig_id
        checklists.append(
            {
                "sourceRef": source_uri,
                "benchmarkId": ingest_lib.truncate(stig_id, ingest_lib.MAX_NAME_LENGTH) or stig_id,
                "revisionStr": ingest_lib.revision_str(meta.get("version"), meta.get("release_info")),
                "reviews": reviews,
                "stats": stats,
                "baseline_meta": meta,
                "baseline_rules": rules,
                "target_data": target_data,
            }
        )

    if not checklists:
        raise ValueError("STIG_INFO element has no SI_DATA for SID_NAME == stigid")

    return {
        "sourceRef": source_uri,
        "target": {
            "name": target["name"],
            "description": target.get("description"),
            "ip": target.get("ip"),
            "fqdn": target.get("fqdn"),
            "mac": target.get("mac"),
            "noncomputing": bool(target.get("noncomputing")),
            "metadata": target.get("metadata") or {},
        },
        "checklists": checklists,
        "errors": errors,
        "target_data": target_data,
    }
