"""Workspace metrics and findings report aggregations."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import access
import kv_client
import validation
from models import KV_STIG_BASELINE_RULES, KV_STIG_CHECKLISTS, KV_STIG_HOSTS, KV_STIG_REVIEWS, STATUSES, now_epoch
from services import baselines as baselines_svc
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import hosts as hosts_svc

DEFAULT_FINDINGS_LIMIT = 500
MAX_FINDINGS_LIMIT = 2000
OPEN_STATUSES = frozenset({"open"})


def _require_read_collection(service, collection_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    grants = grants_svc.query_grants(service, collection_id)
    if not access.user_can_read_collection(rec, session, grants):
        raise KeyError(collection_id)
    return rec


def _parse_int(value: Any, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    if num < minimum:
        return minimum
    if maximum is not None and num > maximum:
        return maximum
    return num


def _parse_status_filter(raw: Optional[str]) -> Optional[Set[str]]:
    if raw is None or str(raw).strip() == "":
        return None
    parts = [p.strip().lower() for p in str(raw).split(",") if p.strip()]
    if not parts:
        return None
    invalid = [p for p in parts if p not in STATUSES]
    if invalid:
        raise ValueError(f"invalid status filter: {', '.join(invalid)}")
    return set(parts)


def _rule_severity_index(service, baseline_ids: Iterable[str]) -> Dict[Tuple[str, str, str], str]:
    """Map (baseline_id, rule_id, group_id) -> severity from baseline rules."""
    rules_coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)
    index: Dict[Tuple[str, str, str], str] = {}
    for baseline_id in baseline_ids:
        if not baseline_id:
            continue
        for rule in kv_client.query_all(rules_coll, {"baseline_id": baseline_id}):
            sev = (rule.get("severity") or "unknown").lower()
            bid = str(rule.get("baseline_id") or baseline_id)
            rid = str(rule.get("rule_id") or "")
            gid = str(rule.get("group_id") or "")
            if rid:
                index[(bid, rid, gid)] = sev
                index[(bid, rid, "")] = sev
            if gid:
                index[(bid, "", gid)] = sev
    return index


def review_severity(
    review: Dict[str, Any], severity_index: Dict[Tuple[str, str, str], str]
) -> str:
    baseline_id = str(review.get("baseline_id") or "")
    rule_id = str(review.get("rule_id") or "")
    group_id = str(review.get("group_id") or "")
    for key in (
        (baseline_id, rule_id, group_id),
        (baseline_id, rule_id, ""),
        (baseline_id, "", group_id),
    ):
        if key in severity_index:
            return severity_index[key]
    return "unknown"


def aggregate_metrics(
    reviews: List[Dict[str, Any]],
    severity_index: Dict[Tuple[str, str, str], str],
    *,
    host_count: int,
    checklist_count: int,
) -> Dict[str, Any]:
    by_status = {status: 0 for status in STATUSES}
    by_severity: Dict[str, int] = {}
    open_by_severity: Dict[str, int] = {}
    valid_count = 0
    for review in reviews:
        status = review.get("status") or "not_reviewed"
        if status not in by_status:
            status = "not_reviewed"
        by_status[status] = by_status.get(status, 0) + 1
        sev = review_severity(review, severity_index)
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if status == "open":
            open_by_severity[sev] = open_by_severity.get(sev, 0) + 1
        if validation.is_valid(review):
            valid_count += 1

    total = len(reviews)
    not_reviewed = by_status.get("not_reviewed", 0)
    reviewed = total - not_reviewed
    percent = round((reviewed / total) * 100.0, 1) if total else 0.0

    return {
        "totals": {
            "hosts": host_count,
            "checklists": checklist_count,
            "reviews": total,
        },
        "completion": {
            "reviewed": reviewed,
            "not_reviewed": not_reviewed,
            "percent_reviewed": percent,
            "valid": valid_count,
            "open_findings": by_status.get("open", 0),
        },
        "by_status": by_status,
        "by_severity": dict(sorted(by_severity.items())),
        "open_by_severity": dict(sorted(open_by_severity.items())),
    }


def collection_metrics(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    collection = _require_read_collection(service, collection_id, session)
    checklists = checklists_svc.list_checklists(service, session, collection_id)
    checklist_ids = [c["_key"] for c in checklists if c.get("_key")]
    baseline_ids = {c.get("baseline_id") for c in checklists if c.get("baseline_id")}

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    reviews: List[Dict[str, Any]] = []
    for checklist_id in checklist_ids:
        reviews.extend(kv_client.query_all(reviews_coll, {"checklist_id": checklist_id}))

    hosts = hosts_svc.list_hosts(service, session, collection_id)
    severity_index = _rule_severity_index(service, baseline_ids)
    metrics = aggregate_metrics(
        reviews,
        severity_index,
        host_count=len(hosts),
        checklist_count=len(checklists),
    )
    return {
        "stig_collection_id": collection_id,
        "collection_name": collection.get("name") or "",
        "generated_at": now_epoch(),
        **metrics,
    }


def _enrich_finding(
    review: Dict[str, Any],
    *,
    checklist: Dict[str, Any],
    host: Dict[str, Any],
    baseline: Dict[str, Any],
    severity: str,
) -> Dict[str, Any]:
    return {
        "_key": review.get("_key"),
        "stig_collection_id": checklist.get("stig_collection_id"),
        "checklist_id": review.get("checklist_id"),
        "host_id": checklist.get("host_id"),
        "hostname": host.get("hostname") or "",
        "baseline_id": review.get("baseline_id") or checklist.get("baseline_id"),
        "baseline_title": baseline.get("title") or "",
        "stig_id": baseline.get("stig_id") or "",
        "group_id": review.get("group_id") or "",
        "rule_id": review.get("rule_id") or "",
        "rule_version": review.get("rule_version") or "",
        "severity": severity,
        "status": review.get("status") or "not_reviewed",
        "finding_details": review.get("finding_details") or "",
        "comments": review.get("comments") or "",
        "valid": validation.is_valid(review),
        "ingest_lock": bool(review.get("ingest_lock")),
        "updated_at": review.get("updated_at"),
        "updated_by": review.get("updated_by") or "",
    }


def collection_findings(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    query = query or {}
    _require_read_collection(service, collection_id, session)

    status_filter = _parse_status_filter(query.get("status"))
    if status_filter is None:
        status_filter = set(OPEN_STATUSES)

    severity_filter = (query.get("severity") or "").strip().lower()
    host_id_filter = (query.get("host_id") or "").strip()
    hostname_filter = (query.get("hostname") or "").strip().casefold()
    baseline_filter = (query.get("baseline_id") or "").strip()
    rule_id_filter = (query.get("rule_id") or "").strip()

    limit = _parse_int(
        query.get("limit"), DEFAULT_FINDINGS_LIMIT, minimum=1, maximum=MAX_FINDINGS_LIMIT
    )
    offset = _parse_int(query.get("offset"), 0, minimum=0)

    checklists = checklists_svc.list_checklists(service, session, collection_id)
    checklist_by_id = {c["_key"]: c for c in checklists if c.get("_key")}

    hosts = hosts_svc.list_hosts(service, session, collection_id)
    host_by_id = {h["_key"]: h for h in hosts if h.get("_key")}

    baselines = {b["_key"]: b for b in baselines_svc.list_baselines(service) if b.get("_key")}
    baseline_ids = {c.get("baseline_id") for c in checklists if c.get("baseline_id")}
    severity_index = _rule_severity_index(service, baseline_ids)

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    rows: List[Dict[str, Any]] = []
    for checklist_id, checklist in checklist_by_id.items():
        host = host_by_id.get(checklist.get("host_id") or "", {})
        if host_id_filter and checklist.get("host_id") != host_id_filter:
            continue
        if hostname_filter:
            host_name = (host.get("hostname") or "").casefold()
            if hostname_filter not in host_name:
                continue
        if baseline_filter and checklist.get("baseline_id") != baseline_filter:
            continue

        for review in kv_client.query_all(reviews_coll, {"checklist_id": checklist_id}):
            status = review.get("status") or "not_reviewed"
            if status not in status_filter:
                continue
            if rule_id_filter and review.get("rule_id") != rule_id_filter:
                continue
            sev = review_severity(review, severity_index)
            if severity_filter and sev != severity_filter:
                continue
            baseline = baselines.get(review.get("baseline_id") or checklist.get("baseline_id") or "", {})
            rows.append(
                _enrich_finding(
                    review,
                    checklist=checklist,
                    host=host,
                    baseline=baseline,
                    severity=sev,
                )
            )

    rows.sort(
        key=lambda row: (
            row.get("hostname") or "",
            row.get("stig_id") or "",
            row.get("group_id") or "",
            row.get("rule_id") or "",
        )
    )
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "stig_collection_id": collection_id,
        "findings": page,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(page) < total,
        },
        "filters": {
            "status": sorted(status_filter),
            "severity": severity_filter or None,
            "host_id": host_id_filter or None,
            "hostname": query.get("hostname") or None,
            "baseline_id": baseline_filter or None,
            "rule_id": rule_id_filter or None,
        },
    }
