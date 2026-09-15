"""Canonical stig:finding event used for HEC and KV reconcile.

The payload is a STIG Manager Watcher review plus the asset, STIG revision,
and rule body needed to synthesize a CKL/CKLB later.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from importers.ingest import result_from_status, status_from_result
from models import check_content_hash, now_epoch, parse_json_field


EXPORT_RULE_FIELDS = (
    "group_id",
    "rule_id",
    "rule_id_src",
    "rule_version",
    "severity",
    "rule_title",
    "discussion",
    "check_content",
    "fix_text",
    "ccis",
    "check_content_hash",
    "group_title",
    "srg_id",
    "weight",
    "check_content_ref",
    "reference_identifier",
    "group_id_src",
    "false_positives",
    "false_negatives",
    "documentable",
    "mitigations",
    "security_override_guidance",
    "potential_impacts",
    "third_party_tools",
    "mitigation_control",
    "responsibility",
    "ia_controls",
)

EXPORT_STIG_FIELDS = (
    "stig_id",
    "title",
    "stig_name",
    "version",
    "release_info",
    "benchmark_date",
    "uuid",
    "description",
    "classification",
    "notice",
    "stig_source",
    "target_key",
    "display_name",
    "reference_identifier",
    "source_type",
    "source_filename",
)


def finding_key(event: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(event.get("collectionId") or "").strip(),
            str(event.get("assetName") or "").strip().casefold(),
            str(event.get("benchmarkId") or "").strip().casefold(),
            str(event.get("ruleId") or event.get("groupId") or "").strip(),
        ]
    )


def _rule_payload(rule: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = dict(rule or {})
    ccis = parse_json_field(src.get("ccis"), default=src.get("ccis") or []) or []
    check = src.get("check_content") or ""
    out = {field: src.get(field) or "" for field in EXPORT_RULE_FIELDS}
    out["ccis"] = ccis if isinstance(ccis, list) else []
    out["severity"] = (src.get("severity") or "medium").lower()
    out["weight"] = str(src.get("weight") or "10.0")
    out["documentable"] = src.get("documentable") or "false"
    if not out["check_content_hash"] and check:
        out["check_content_hash"] = check_content_hash(check)
    if not out["rule_id"]:
        out["rule_id"] = src.get("rule_id_src") or ""
    if not out["rule_id_src"]:
        out["rule_id_src"] = src.get("rule_id") or ""
    return out


def _stig_payload(meta: Optional[Dict[str, Any]], benchmark_id: str = "") -> Dict[str, Any]:
    src = dict(meta or {})
    out = {field: src.get(field) or "" for field in EXPORT_STIG_FIELDS}
    if not out["stig_id"]:
        out["stig_id"] = benchmark_id
    return out


def _asset_payload(target: Dict[str, Any], target_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    td = dict(target_data or {})
    metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
    if not td:
        td = {
            "target_type": "Non-Computing" if target.get("noncomputing") else "Computing",
            "host_name": target.get("name") or "",
            "ip_address": target.get("ip") or "",
            "mac_address": target.get("mac") or "",
            "fqdn": target.get("fqdn") or "",
            "comments": target.get("description") or "",
            "role": metadata.get("cklRole") or "None",
            "is_web_database": metadata.get("cklWebOrDatabase") == "true",
            "technology_area": metadata.get("cklTechArea") or "",
            "web_db_site": metadata.get("cklWebDbSite") or "",
            "web_db_instance": metadata.get("cklWebDbInstance") or "",
        }
    return {
        "name": target.get("name") or td.get("host_name") or "",
        "ip": target.get("ip") or td.get("ip_address") or "",
        "fqdn": target.get("fqdn") or td.get("fqdn") or "",
        "mac": target.get("mac") or td.get("mac_address") or "",
        "noncomputing": bool(target.get("noncomputing")),
        "description": target.get("description") or td.get("comments") or "",
        "metadata": metadata,
        "target_data": td,
    }


def build_finding_event(
    review: Dict[str, Any],
    *,
    rule: Optional[Dict[str, Any]] = None,
    stig: Optional[Dict[str, Any]] = None,
    target: Optional[Dict[str, Any]] = None,
    target_data: Optional[Dict[str, Any]] = None,
    collection_id: str = "",
    collection_name: str = "",
    source_ref: str = "",
    source_product: str = "stigs_in_splunk",
    revision: Optional[str] = None,
    host_id: str = "",
    checklist_id: str = "",
    baseline_id: str = "",
) -> Dict[str, Any]:
    target = target or {}
    asset = _asset_payload(target, target_data)
    rule_id = review.get("ruleId") or (rule or {}).get("rule_id_src") or (rule or {}).get("rule_id") or ""
    group_id = review.get("groupId") or (rule or {}).get("group_id") or ""
    benchmark_id = (stig or {}).get("stig_id") or ""
    result = review.get("result") or result_from_status(review.get("status")) or "notchecked"
    event = {
        "time": now_epoch(),
        "source_product": source_product,
        "sourceRef": source_ref or review.get("sourceRef") or "",
        "collectionId": collection_id,
        "collectionName": collection_name,
        "assetName": asset.get("name") or "",
        "asset": asset,
        "benchmarkId": benchmark_id,
        "revisionStr": revision,
        "stig": _stig_payload(stig, benchmark_id),
        "ruleId": rule_id,
        "groupId": group_id,
        "result": result,
        "detail": review.get("detail") or review.get("finding_details") or "",
        "comment": review.get("comment") or review.get("comments") or "",
        "status": review.get("status") or "saved",
        "resultEngine": review.get("resultEngine"),
        "rule": _rule_payload(rule),
        "hostId": host_id,
        "checklistId": checklist_id,
        "baselineId": baseline_id,
    }
    return event


def events_from_parsed(
    parsed: Dict[str, Any],
    collection_id: str,
    source_uri: str = "",
    source_product: str = "stigs_in_splunk",
    collection_name: str = "",
) -> List[Dict[str, Any]]:
    target = parsed.get("target") or {}
    target_data = parsed.get("target_data") or {}
    events: List[Dict[str, Any]] = []
    for checklist in parsed.get("checklists") or []:
        meta = checklist.get("baseline_meta") or {}
        rules = { _rule_index_key(rule): rule for rule in (checklist.get("baseline_rules") or []) }
        td = checklist.get("target_data") or target_data
        for review in checklist.get("reviews") or []:
            rule = (
                rules.get(review.get("ruleId") or "")
                or rules.get(review.get("groupId") or "")
                or _lookup_rule(checklist.get("baseline_rules") or [], review)
            )
            events.append(
                build_finding_event(
                    review,
                    rule=rule,
                    stig=meta,
                    target=target,
                    target_data=td,
                    collection_id=collection_id,
                    collection_name=collection_name,
                    source_ref=source_uri or checklist.get("sourceRef") or "",
                    source_product=source_product,
                    revision=checklist.get("revisionStr"),
                )
            )
    return events


def _rule_index_key(rule: Dict[str, Any]) -> str:
    return str(rule.get("rule_id_src") or rule.get("rule_id") or rule.get("group_id") or "")


def _lookup_rule(rules: List[Dict[str, Any]], review: Dict[str, Any]) -> Dict[str, Any]:
    want = {
        str(review.get("ruleId") or ""),
        str(review.get("groupId") or ""),
    }
    extra = set()
    for key in list(want):
        if key.endswith("_rule"):
            extra.add(key[: -len("_rule")])
        elif key:
            extra.add(key + "_rule")
    want.update(extra)
    for rule in rules:
        keys = {
            str(rule.get("rule_id") or ""),
            str(rule.get("rule_id_src") or ""),
            str(rule.get("group_id") or ""),
        }
        if want.intersection(keys):
            return rule
    return {}


def normalize_finding_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Accept slim Watcher posts or fat HEC events."""
    if not isinstance(raw, dict):
        raise ValueError("finding event must be an object")
    event = dict(raw)
    if event.get("event") and isinstance(event["event"], dict):
        wrapped = dict(event["event"])
        wrapped.setdefault("time", event.get("time"))
        event = wrapped
    asset = event.get("asset") if isinstance(event.get("asset"), dict) else {}
    stig = event.get("stig") if isinstance(event.get("stig"), dict) else {}
    rule = event.get("rule") if isinstance(event.get("rule"), dict) else {}
    target_data = asset.get("target_data") if isinstance(asset.get("target_data"), dict) else {}
    if not event.get("assetName"):
        event["assetName"] = asset.get("name") or target_data.get("host_name") or ""
    if not event.get("benchmarkId"):
        event["benchmarkId"] = stig.get("stig_id") or ""
    if not event.get("ruleId"):
        event["ruleId"] = rule.get("rule_id_src") or rule.get("rule_id") or ""
    if not event.get("groupId"):
        event["groupId"] = rule.get("group_id") or ""
    if not event.get("result"):
        event["result"] = result_from_status(event.get("status")) or "notchecked"
    event["detail"] = event.get("detail") or event.get("finding_details") or ""
    event["comment"] = event.get("comment") or event.get("comments") or ""
    event["stig"] = _stig_payload(stig, event.get("benchmarkId") or "")
    event["rule"] = _rule_payload(rule) if rule else _rule_payload(
        {
            "rule_id": event.get("ruleId"),
            "rule_id_src": event.get("ruleId"),
            "group_id": event.get("groupId"),
        }
    )
    if not asset:
        event["asset"] = _asset_payload(
            {
                "name": event.get("assetName") or "",
                "ip": event.get("ip") or event.get("ip_address"),
                "fqdn": event.get("fqdn"),
                "mac": event.get("mac") or event.get("mac_address"),
            },
            target_data or event.get("target_data"),
        )
    else:
        event["asset"] = _asset_payload(
            {
                "name": asset.get("name") or event.get("assetName"),
                "ip": asset.get("ip"),
                "fqdn": asset.get("fqdn"),
                "mac": asset.get("mac"),
                "noncomputing": asset.get("noncomputing"),
                "description": asset.get("description"),
                "metadata": asset.get("metadata") or {},
            },
            target_data,
        )
    if not event.get("assetName"):
        raise ValueError("finding event missing assetName")
    if not event.get("benchmarkId"):
        raise ValueError("finding event missing benchmarkId")
    if not event.get("ruleId") and not event.get("groupId"):
        raise ValueError("finding event missing ruleId")
    event["_key"] = finding_key(event)
    event["_status"] = status_from_result(event.get("result"))
    return event


def event_has_export_body(event: Dict[str, Any]) -> bool:
    rule = event.get("rule") or {}
    stig = event.get("stig") or {}
    asset = event.get("asset") or {}
    return bool(
        (rule.get("rule_title") or rule.get("check_content"))
        and (stig.get("stig_id") or event.get("benchmarkId"))
        and (asset.get("name") or event.get("assetName"))
    )
