"""Workspace metrics and findings report aggregations."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import access
import kv_client
import review_workflow
import validation
from models import (
    KV_STIG_BASELINE_RULES,
    KV_STIG_CHECKLISTS,
    KV_STIG_HOSTS,
    KV_STIG_REVIEWS,
    STATUSES,
    now_epoch,
    parse_json_field,
)
from exporters.poam import (
    POAM_COLUMNS,
    findings_to_poam_rows,
    poam_to_csv,
    poam_xlsx_payload,
    safe_poam_filename,
)
from services import baselines as baselines_svc
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import hosts as hosts_svc

DEFAULT_FINDINGS_LIMIT = 500
MAX_FINDINGS_LIMIT = 2000
OPEN_STATUSES = frozenset({"open"})
UNREVIEWED_STATUS = "not_reviewed"
UNREVIEWED_DEFINITION = (
    "A review counts as unreviewed when its assessor status is not_reviewed "
    "(CKL Not Reviewed / STIG Manager notchecked). Rows with open, not_a_finding, "
    "or not_applicable are excluded. Governance workflow (submitted/accepted/rejected) "
    "does not override status; only not_reviewed rows appear in these reports. "
    "Host and checklist visibility follows the same grant ACL filters as metrics and findings."
)


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


def _rule_meta_index(
    service, baseline_ids: Iterable[str]
) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Map (baseline_id, rule_id, group_id) -> rule metadata from baseline rules."""
    rules_coll = kv_client.get_collection(service, KV_STIG_BASELINE_RULES)
    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for baseline_id in baseline_ids:
        if not baseline_id:
            continue
        for rule in kv_client.query_all(rules_coll, {"baseline_id": baseline_id}):
            bid = str(rule.get("baseline_id") or baseline_id)
            rid = str(rule.get("rule_id") or "")
            gid = str(rule.get("group_id") or "")
            ccis = parse_json_field(rule.get("ccis"), default=[]) or []
            meta = {
                "rule_title": rule.get("rule_title") or "",
                "severity": (rule.get("severity") or "unknown").lower(),
                "rule_version": rule.get("rule_version") or "",
                "ccis": ccis if isinstance(ccis, list) else [],
                "group_title": rule.get("group_title") or "",
            }
            if rid:
                index[(bid, rid, gid)] = meta
                index[(bid, rid, "")] = meta
            if gid:
                index[(bid, "", gid)] = meta
    return index


def _severity_index_from_meta(
    rule_meta_index: Dict[Tuple[str, str, str], Dict[str, Any]],
) -> Dict[Tuple[str, str, str], str]:
    return {
        key: (value.get("severity") or "unknown")
        for key, value in rule_meta_index.items()
    }


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
    open_status_count = 0
    open_governance_count = 0
    for review in reviews:
        status = review.get("status") or "not_reviewed"
        if status not in by_status:
            status = "not_reviewed"
        by_status[status] = by_status.get(status, 0) + 1
        sev = review_severity(review, severity_index)
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if status == "open":
            open_status_count += 1
            if review_workflow.is_governance_open_finding(review):
                open_governance_count += 1
                open_by_severity[sev] = open_by_severity.get(sev, 0) + 1
        if validation.is_valid(review):
            valid_count += 1

    total = len(reviews)
    not_reviewed = by_status.get("not_reviewed", 0)
    reviewed = total - not_reviewed
    percent = round((reviewed / total) * 100.0, 1) if total else 0.0
    workflow = review_workflow.counts_for_metrics(reviews)

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
            "open_findings": open_governance_count,
            "open_findings_by_status": open_status_count,
        },
        "workflow": workflow,
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
    rule_meta_index = _rule_meta_index(service, baseline_ids)
    severity_index = _severity_index_from_meta(rule_meta_index)
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


def rollup_aggregate_metrics(metric_parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum multiple ``aggregate_metrics`` payloads into org-wide totals."""
    totals = {"hosts": 0, "checklists": 0, "reviews": 0}
    completion_keys = (
        "reviewed",
        "not_reviewed",
        "valid",
        "open_findings",
        "open_findings_by_status",
    )
    completion = {key: 0 for key in completion_keys}
    workflow_keys = ("draft", "submitted", "accepted", "rejected", "open_unaccepted")
    workflow = {key: 0 for key in workflow_keys}
    by_status = {status: 0 for status in STATUSES}
    by_severity: Dict[str, int] = {}
    open_by_severity: Dict[str, int] = {}

    for part in metric_parts:
        part_totals = part.get("totals") or {}
        for key in totals:
            totals[key] += int(part_totals.get(key) or 0)
        part_completion = part.get("completion") or {}
        for key in completion_keys:
            completion[key] += int(part_completion.get(key) or 0)
        part_workflow = part.get("workflow") or {}
        for key in workflow_keys:
            workflow[key] += int(part_workflow.get(key) or 0)
        for status, count in (part.get("by_status") or {}).items():
            if status in by_status:
                by_status[status] += int(count or 0)
        for sev, count in (part.get("by_severity") or {}).items():
            by_severity[sev] = by_severity.get(sev, 0) + int(count or 0)
        for sev, count in (part.get("open_by_severity") or {}).items():
            open_by_severity[sev] = open_by_severity.get(sev, 0) + int(count or 0)

    total_reviews = totals["reviews"]
    reviewed = completion["reviewed"]
    completion["percent_reviewed"] = (
        round((reviewed / total_reviews) * 100.0, 1) if total_reviews else 0.0
    )

    return {
        "totals": totals,
        "completion": completion,
        "workflow": workflow,
        "by_status": by_status,
        "by_severity": dict(sorted(by_severity.items())),
        "open_by_severity": dict(sorted(open_by_severity.items())),
    }


def _workspace_metrics_row(metrics: Dict[str, Any], collection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stig_collection_id": metrics.get("stig_collection_id")
        or collection.get("_key")
        or "",
        "collection_name": metrics.get("collection_name")
        or collection.get("name")
        or "",
        "totals": metrics.get("totals") or {},
        "completion": metrics.get("completion") or {},
        "workflow": metrics.get("workflow") or {},
        "by_status": metrics.get("by_status") or {},
        "by_severity": metrics.get("by_severity") or {},
        "open_by_severity": metrics.get("open_by_severity") or {},
    }


def meta_collection_metrics(
    service, session: Dict[str, Any], query: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Aggregate dashboard metrics across workspaces the session may read."""
    query = query or {}
    limit = _parse_int((query or {}).get("limit"), default=500, minimum=1, maximum=500)
    offset = _parse_int((query or {}).get("offset"), default=0, minimum=0)

    collections = collections_svc.list_collections(service, session)
    collections = sorted(
        collections, key=lambda rec: (rec.get("name") or rec.get("_key") or "").lower()
    )
    total_visible = len(collections)
    page = collections[offset : offset + limit]

    workspaces: List[Dict[str, Any]] = []
    metric_parts: List[Dict[str, Any]] = []
    for coll in page:
        cid = coll.get("_key") or ""
        if not cid:
            continue
        metrics = collection_metrics(service, cid, session)
        workspaces.append(_workspace_metrics_row(metrics, coll))
        metric_parts.append(metrics)

    return {
        "generated_at": now_epoch(),
        "workspace_count": total_visible,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(workspaces),
            "total": total_visible,
        },
        "summary": rollup_aggregate_metrics(metric_parts),
        "workspaces": workspaces,
    }


def meta_collection_metrics_summary(
    service, session: Dict[str, Any], query: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Org-wide rollup without per-workspace rows (same ACL as meta metrics)."""
    full = meta_collection_metrics(service, session, query)
    return {
        "generated_at": full["generated_at"],
        "workspace_count": full["workspace_count"],
        "pagination": full["pagination"],
        "summary": full["summary"],
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


def _collection_workspace_context(
    service, collection_id: str, session: Dict[str, Any]
) -> Dict[str, Any]:
    checklists = checklists_svc.list_checklists(service, session, collection_id)
    hosts = hosts_svc.list_hosts(service, session, collection_id)
    baselines = {b["_key"]: b for b in baselines_svc.list_baselines(service) if b.get("_key")}
    baseline_ids = {c.get("baseline_id") for c in checklists if c.get("baseline_id")}
    rule_meta_index = _rule_meta_index(service, baseline_ids)
    return {
        "checklist_by_id": {c["_key"]: c for c in checklists if c.get("_key")},
        "host_by_id": {h["_key"]: h for h in hosts if h.get("_key")},
        "baselines": baselines,
        "baseline_ids": baseline_ids,
        "rule_meta_index": rule_meta_index,
        "severity_index": _severity_index_from_meta(rule_meta_index),
    }


def _parse_findings_filters(query: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    query = query or {}
    status_filter = _parse_status_filter(query.get("status"))
    if status_filter is None:
        status_filter = set(OPEN_STATUSES)
    return {
        "status_filter": status_filter,
        "severity_filter": (query.get("severity") or "").strip().lower(),
        "host_id_filter": (query.get("host_id") or "").strip(),
        "hostname_filter": (query.get("hostname") or "").strip().casefold(),
        "baseline_filter": (query.get("baseline_id") or "").strip(),
        "rule_id_filter": (query.get("rule_id") or "").strip(),
        "raw": query,
    }


def _filters_response(parsed: Dict[str, Any]) -> Dict[str, Any]:
    query = parsed["raw"]
    return {
        "status": sorted(parsed["status_filter"]),
        "severity": parsed["severity_filter"] or None,
        "host_id": parsed["host_id_filter"] or None,
        "hostname": query.get("hostname") or None,
        "baseline_id": parsed["baseline_filter"] or None,
        "rule_id": parsed["rule_id_filter"] or None,
    }


def _list_collection_findings(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
    *,
    ctx: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    parsed = _parse_findings_filters(query)
    status_filter = parsed["status_filter"]
    severity_filter = parsed["severity_filter"]
    host_id_filter = parsed["host_id_filter"]
    hostname_filter = parsed["hostname_filter"]
    baseline_filter = parsed["baseline_filter"]
    rule_id_filter = parsed["rule_id_filter"]

    if ctx is None:
        ctx = _collection_workspace_context(service, collection_id, session)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    rows: List[Dict[str, Any]] = []
    for checklist_id, checklist in ctx["checklist_by_id"].items():
        host = ctx["host_by_id"].get(checklist.get("host_id") or "", {})
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
            if status in OPEN_STATUSES and not review_workflow.is_governance_open_finding(
                review
            ):
                continue
            if rule_id_filter and review.get("rule_id") != rule_id_filter:
                continue
            sev = review_severity(review, ctx["severity_index"])
            if severity_filter and sev != severity_filter:
                continue
            baseline = ctx["baselines"].get(
                review.get("baseline_id") or checklist.get("baseline_id") or "", {}
            )
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
    return rows, _filters_response(parsed), ctx


def collection_findings(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    query = query or {}
    _require_read_collection(service, collection_id, session)

    limit = _parse_int(
        query.get("limit"), DEFAULT_FINDINGS_LIMIT, minimum=1, maximum=MAX_FINDINGS_LIMIT
    )
    offset = _parse_int(query.get("offset"), 0, minimum=0)

    rows, filters, _ctx = _list_collection_findings(
        service, collection_id, session, query
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
        "filters": filters,
    }


def _parse_group_by(raw: Optional[str]) -> Set[str]:
    allowed = frozenset({"group_id", "rule_id", "cci"})
    if raw is None or str(raw).strip() == "":
        return set(allowed)
    parts = {p.strip().lower() for p in str(raw).split(",") if p.strip()}
    invalid = parts - allowed
    if invalid:
        raise ValueError(f"invalid group_by: {', '.join(sorted(invalid))}")
    return parts


def _rule_meta_for_finding(
    finding: Dict[str, Any], rule_meta_index: Dict[Tuple[str, str, str], Dict[str, Any]]
) -> Dict[str, Any]:
    baseline_id = str(finding.get("baseline_id") or "")
    rule_id = str(finding.get("rule_id") or "")
    group_id = str(finding.get("group_id") or "")
    for key in (
        (baseline_id, rule_id, group_id),
        (baseline_id, rule_id, ""),
        (baseline_id, "", group_id),
    ):
        if key in rule_meta_index:
            return rule_meta_index[key]
    return {}


def _aggregate_bucket(
    buckets: Dict[str, Dict[str, Any]],
    key: str,
    *,
    group_id: str = "",
    rule_id: str = "",
    cci: str = "",
    severity: str = "",
    hostname: str = "",
    baseline_id: str = "",
    stig_id: str = "",
    baseline_title: str = "",
) -> None:
    if not key:
        return
    bucket = buckets.setdefault(
        key,
        {
            "count": 0,
            "host_count": 0,
            "group_id": group_id,
            "rule_id": rule_id,
            "cci": cci,
            "severity": severity,
            "baseline_id": baseline_id,
            "stig_id": stig_id,
            "baseline_title": baseline_title,
            "_hosts": set(),
        },
    )
    bucket["count"] += 1
    if hostname:
        bucket["_hosts"].add(hostname)
    bucket["host_count"] = len(bucket["_hosts"])
    if severity and not bucket.get("severity"):
        bucket["severity"] = severity
    if group_id and not bucket.get("group_id"):
        bucket["group_id"] = group_id
    if rule_id and not bucket.get("rule_id"):
        bucket["rule_id"] = rule_id
    if baseline_id and not bucket.get("baseline_id"):
        bucket["baseline_id"] = baseline_id
    if stig_id and not bucket.get("stig_id"):
        bucket["stig_id"] = stig_id
    if baseline_title and not bucket.get("baseline_title"):
        bucket["baseline_title"] = baseline_title


def _finalize_buckets(buckets: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for bucket in buckets.values():
        hosts = bucket.pop("_hosts", set())
        row = dict(bucket)
        row["hostnames"] = sorted(hosts)
        rows.append(row)
    rows.sort(
        key=lambda r: (
            -int(r.get("count") or 0),
            r.get("stig_id") or "",
            r.get("baseline_id") or "",
            r.get("group_id") or "",
            r.get("rule_id") or "",
            r.get("cci") or "",
        )
    )
    return rows


def _baseline_rule_bucket_key(baseline_id: str, rule_id: str) -> str:
    return f"{baseline_id}\x1f{rule_id}"


def _baseline_group_bucket_key(baseline_id: str, group_id: str) -> str:
    return f"{baseline_id}\x1f{group_id}"


def splunk_poam_alternative(collection_id: str) -> Dict[str, Any]:
    """SPL hints for governance-open exports (not full POA&M column parity)."""
    cid = collection_id.replace('"', '\\"')
    governance = (
        "status=open (workflow_state!=accepted OR NOT workflow_state=*)"
    )
    base = (
        "| inputlookup stig_checklists "
        f'| search stig_collection_id="{cid}" '
        "| rename _key AS checklist_id "
        "| join type=inner checklist_id [ | inputlookup stig_reviews "
        f"| search {governance} ] "
        "| lookup stig_hosts _key AS host_id OUTPUT hostname "
    )
    return {
        "governance_filter": governance,
        "note": (
            "Matches REST intent: open assessor status excluding owner-accepted "
            "(workflow_state=accepted). Legacy rows with no workflow_state are "
            "treated as draft in Python and included here via NOT workflow_state=*. "
            "POA&M columns (rule title, CCI) require joining stig_baseline_rules; "
            "use GET /stig_collections/{id}/poam for enriched export."
        ),
        "findings_table_spl": base + "| table hostname baseline_id group_id rule_id finding_details comments",
        "outputcsv_example": base + "| outputcsv stig_governance_open_findings.csv",
        "enriched_spl": (
            base
            + "| lookup stig_baseline_rules baseline_id rule_id OUTPUT rule_title ccis severity "
            "| table hostname stig_id baseline_id group_id rule_id severity rule_title ccis finding_details"
        ),
    }


def collection_findings_aggregate(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Governance-open findings counts grouped by rule_id, group_id, and/or CCI."""
    query = dict(query or {})
    query.setdefault("status", "open")
    _require_read_collection(service, collection_id, session)
    group_by = _parse_group_by(query.get("group_by"))
    rows, filters, ctx = _list_collection_findings(
        service, collection_id, session, query
    )
    rule_meta_index = ctx["rule_meta_index"]

    by_group: Dict[str, Dict[str, Any]] = {}
    by_rule: Dict[str, Dict[str, Any]] = {}
    by_cci: Dict[str, Dict[str, Any]] = {}

    for finding in rows:
        hostname = finding.get("hostname") or ""
        group_id = finding.get("group_id") or ""
        rule_id = finding.get("rule_id") or ""
        baseline_id = str(finding.get("baseline_id") or "")
        stig_id = finding.get("stig_id") or ""
        baseline_title = finding.get("baseline_title") or ""
        severity = finding.get("severity") or "unknown"
        meta = _rule_meta_for_finding(finding, rule_meta_index)
        ccis = meta.get("ccis") or []
        if not ccis:
            ccis = [""]

        if "group_id" in group_by and group_id and baseline_id:
            _aggregate_bucket(
                by_group,
                _baseline_group_bucket_key(baseline_id, group_id),
                group_id=group_id,
                rule_id=rule_id,
                severity=severity,
                hostname=hostname,
                baseline_id=baseline_id,
                stig_id=stig_id,
                baseline_title=baseline_title,
            )
        if "rule_id" in group_by and rule_id and baseline_id:
            _aggregate_bucket(
                by_rule,
                _baseline_rule_bucket_key(baseline_id, rule_id),
                group_id=group_id,
                rule_id=rule_id,
                severity=severity,
                hostname=hostname,
                baseline_id=baseline_id,
                stig_id=stig_id,
                baseline_title=baseline_title,
            )
        if "cci" in group_by:
            for cci in ccis:
                cci_key = str(cci).strip() or "(no cci)"
                _aggregate_bucket(
                    by_cci,
                    cci_key,
                    group_id=group_id,
                    rule_id=rule_id,
                    cci=cci_key if cci_key != "(no cci)" else "",
                    severity=severity,
                    hostname=hostname,
                )

    out: Dict[str, Any] = {
        "stig_collection_id": collection_id,
        "generated_at": now_epoch(),
        "open_findings_total": len(rows),
        "group_by": sorted(group_by),
        "filters": filters,
        "scan_note": (
            "Full workspace scan of matching reviews (no pagination). "
            "Large workspaces may prefer Splunk lookups or filtered queries."
        ),
    }
    if "group_id" in group_by:
        out["by_group_id"] = _finalize_buckets(by_group)
    if "rule_id" in group_by:
        out["by_rule_id"] = _finalize_buckets(by_rule)
    if "cci" in group_by:
        out["by_cci"] = _finalize_buckets(by_cci)
    return out


def collection_poam(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """POA&M rows from governance-open findings (open ∧ not accepted)."""
    query = dict(query or {})
    query.setdefault("status", "open")
    collection = _require_read_collection(service, collection_id, session)
    findings, filters, ctx = _list_collection_findings(
        service, collection_id, session, query
    )
    rows = findings_to_poam_rows(findings, ctx["rule_meta_index"])
    fmt = (query.get("format") or "json").strip().lower()
    filename = safe_poam_filename(collection_id, "xlsx" if fmt == "xlsx" else "csv")
    row_count = len(rows)

    if fmt == "csv":
        return {
            "format": "csv",
            "filename": filename,
            "content": poam_to_csv(rows),
            "row_count": row_count,
            "filters": filters,
        }
    if fmt == "xlsx":
        payload = poam_xlsx_payload(rows, filename)
        payload["filters"] = filters
        payload["row_count"] = row_count
        return payload

    return {
        "stig_collection_id": collection_id,
        "collection_name": collection.get("name") or "",
        "generated_at": now_epoch(),
        "format": "json",
        "columns": POAM_COLUMNS,
        "rows": rows,
        "row_count": row_count,
        "filters": filters,
        "splunk_alternative": splunk_poam_alternative(collection_id),
    }


def _parse_unreviewed_filters(query: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    query = query or {}
    return {
        "host_id_filter": (query.get("host_id") or "").strip(),
        "hostname_filter": (query.get("hostname") or "").strip().casefold(),
        "baseline_filter": (query.get("baseline_id") or "").strip(),
        "rule_id_filter": (query.get("rule_id") or "").strip(),
        "group_id_filter": (query.get("group_id") or "").strip(),
        "severity_filter": (query.get("severity") or "").strip().lower(),
        "raw": query,
    }


def _unreviewed_filters_response(parsed: Dict[str, Any]) -> Dict[str, Any]:
    query = parsed["raw"]
    return {
        "host_id": parsed["host_id_filter"] or None,
        "hostname": query.get("hostname") or None,
        "baseline_id": parsed["baseline_filter"] or None,
        "rule_id": parsed["rule_id_filter"] or None,
        "group_id": parsed["group_id_filter"] or None,
        "severity": parsed["severity_filter"] or None,
    }


def _list_unreviewed_rows(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
    *,
    ctx: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    parsed = _parse_unreviewed_filters(query)
    if ctx is None:
        ctx = _collection_workspace_context(service, collection_id, session)
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    rows: List[Dict[str, Any]] = []
    for checklist_id, checklist in ctx["checklist_by_id"].items():
        host = ctx["host_by_id"].get(checklist.get("host_id") or "", {})
        if parsed["host_id_filter"] and checklist.get("host_id") != parsed["host_id_filter"]:
            continue
        if parsed["hostname_filter"]:
            host_name = (host.get("hostname") or "").casefold()
            if parsed["hostname_filter"] not in host_name:
                continue
        if parsed["baseline_filter"] and checklist.get("baseline_id") != parsed["baseline_filter"]:
            continue

        baseline_id = str(checklist.get("baseline_id") or "")
        baseline = ctx["baselines"].get(baseline_id, {})
        for review in kv_client.query_all(reviews_coll, {"checklist_id": checklist_id}):
            status = review.get("status") or UNREVIEWED_STATUS
            if status != UNREVIEWED_STATUS:
                continue
            group_id = review.get("group_id") or ""
            rule_id = review.get("rule_id") or ""
            if parsed["rule_id_filter"] and rule_id != parsed["rule_id_filter"]:
                continue
            if parsed["group_id_filter"] and group_id != parsed["group_id_filter"]:
                continue
            sev = review_severity(review, ctx["severity_index"])
            if parsed["severity_filter"] and sev != parsed["severity_filter"]:
                continue
            meta = _rule_meta_for_finding(
                {
                    "baseline_id": review.get("baseline_id") or baseline_id,
                    "rule_id": rule_id,
                    "group_id": group_id,
                },
                ctx["rule_meta_index"],
            )
            rows.append(
                {
                    "host_id": checklist.get("host_id") or "",
                    "hostname": host.get("hostname") or "",
                    "baseline_id": review.get("baseline_id") or baseline_id,
                    "stig_id": baseline.get("stig_id") or "",
                    "baseline_title": baseline.get("title") or "",
                    "group_id": group_id,
                    "rule_id": rule_id,
                    "severity": sev,
                    "rule_title": meta.get("rule_title") or "",
                    "group_title": meta.get("group_title") or "",
                }
            )
    rows.sort(
        key=lambda row: (
            row.get("hostname") or "",
            row.get("stig_id") or "",
            row.get("group_id") or "",
            row.get("rule_id") or "",
        )
    )
    return rows, _unreviewed_filters_response(parsed), ctx


def splunk_unreviewed_alternative(collection_id: str) -> Dict[str, Any]:
    cid = collection_id.replace('"', '\\"')
    base = (
        "| inputlookup stig_checklists "
        f'| search stig_collection_id="{cid}" '
        "| rename _key AS checklist_id "
        "| join type=inner checklist_id [ | inputlookup stig_reviews "
        '| search status=not_reviewed ] '
        "| lookup stig_hosts _key AS host_id OUTPUT hostname "
    )
    return {
        "definition": UNREVIEWED_DEFINITION,
        "by_host_baseline_spl": (
            base
            + "| stats count AS unreviewed_count by hostname baseline_id "
            + "| sort hostname baseline_id"
        ),
        "by_rule_spl": (
            base
            + "| stats count AS unreviewed_count dc(hostname) AS host_count by "
            "baseline_id group_id rule_id "
            + "| sort -unreviewed_count baseline_id group_id rule_id"
        ),
        "outputcsv_example": base + "| outputcsv stig_unreviewed_reviews.csv",
    }


def collection_unreviewed_assets(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-host unreviewed rule counts with per-baseline breakdown."""
    _require_read_collection(service, collection_id, session)
    rows, filters, _ctx = _list_unreviewed_rows(service, collection_id, session, query)
    by_host: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        host_id = row.get("host_id") or ""
        if not host_id:
            continue
        asset = by_host.setdefault(
            host_id,
            {
                "host_id": host_id,
                "hostname": row.get("hostname") or "",
                "unreviewed_count": 0,
                "_by_baseline": {},
            },
        )
        asset["unreviewed_count"] += 1
        baseline_id = str(row.get("baseline_id") or "")
        if baseline_id:
            bl = asset["_by_baseline"].setdefault(
                baseline_id,
                {
                    "baseline_id": baseline_id,
                    "stig_id": row.get("stig_id") or "",
                    "baseline_title": row.get("baseline_title") or "",
                    "unreviewed_count": 0,
                },
            )
            bl["unreviewed_count"] += 1
            if row.get("stig_id") and not bl.get("stig_id"):
                bl["stig_id"] = row.get("stig_id")
            if row.get("baseline_title") and not bl.get("baseline_title"):
                bl["baseline_title"] = row.get("baseline_title")

    assets: List[Dict[str, Any]] = []
    for asset in by_host.values():
        by_baseline = sorted(
            asset.pop("_by_baseline", {}).values(),
            key=lambda b: (b.get("stig_id") or "", b.get("baseline_id") or ""),
        )
        asset["by_baseline"] = by_baseline
        assets.append(asset)
    assets.sort(key=lambda a: (a.get("hostname") or "", a.get("host_id") or ""))

    return {
        "stig_collection_id": collection_id,
        "generated_at": now_epoch(),
        "definition": UNREVIEWED_DEFINITION,
        "total_unreviewed": len(rows),
        "asset_count": len(assets),
        "filters": filters,
        "assets": assets,
        "splunk_alternative": splunk_unreviewed_alternative(collection_id),
    }


def collection_unreviewed_rules(
    service,
    collection_id: str,
    session: Dict[str, Any],
    query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-rule unreviewed counts with host coverage (STIG Manager rules report shape)."""
    _require_read_collection(service, collection_id, session)
    rows, filters, _ctx = _list_unreviewed_rows(service, collection_id, session, query)
    by_rule: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        baseline_id = str(row.get("baseline_id") or "")
        rule_id = row.get("rule_id") or ""
        group_id = row.get("group_id") or ""
        if not baseline_id or not rule_id:
            continue
        key = _baseline_rule_bucket_key(baseline_id, rule_id)
        bucket = by_rule.setdefault(
            key,
            {
                "baseline_id": baseline_id,
                "stig_id": row.get("stig_id") or "",
                "baseline_title": row.get("baseline_title") or "",
                "group_id": group_id,
                "rule_id": rule_id,
                "rule_title": row.get("rule_title") or "",
                "group_title": row.get("group_title") or "",
                "severity": row.get("severity") or "unknown",
                "unreviewed_count": 0,
                "_hosts": set(),
            },
        )
        bucket["unreviewed_count"] += 1
        hostname = row.get("hostname") or ""
        if hostname:
            bucket["_hosts"].add(hostname)
        if group_id and not bucket.get("group_id"):
            bucket["group_id"] = group_id
        if row.get("rule_title") and not bucket.get("rule_title"):
            bucket["rule_title"] = row.get("rule_title")
        if row.get("group_title") and not bucket.get("group_title"):
            bucket["group_title"] = row.get("group_title")
        if row.get("severity") and bucket.get("severity") == "unknown":
            bucket["severity"] = row.get("severity")

    rules: List[Dict[str, Any]] = []
    for bucket in by_rule.values():
        hosts = bucket.pop("_hosts", set())
        bucket["host_count"] = len(hosts)
        bucket["hostnames"] = sorted(hosts)
        rules.append(bucket)
    rules.sort(
        key=lambda r: (
            -int(r.get("unreviewed_count") or 0),
            r.get("stig_id") or "",
            r.get("baseline_id") or "",
            r.get("group_id") or "",
            r.get("rule_id") or "",
        )
    )

    return {
        "stig_collection_id": collection_id,
        "generated_at": now_epoch(),
        "definition": UNREVIEWED_DEFINITION,
        "total_unreviewed": len(rows),
        "rule_count": len(rules),
        "filters": filters,
        "rules": rules,
        "splunk_alternative": splunk_unreviewed_alternative(collection_id),
    }
