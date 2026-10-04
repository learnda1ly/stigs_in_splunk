"""Execute review aging rules (dry-run by default; delete requires explicit execute)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import audit
import kv_client
import review_workflow
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_HOSTS,
    KV_STIG_REVIEWS,
    KV_STIG_REVIEW_HISTORY,
    kv_record,
    now_epoch,
    parse_json_field,
)
from services import baselines as baselines_svc
from services import collections as collections_svc
from services import reporting as reporting_svc
from services import review_aging as aging_svc
from services import review_history as review_history_svc

AGING_ACTOR = "review_aging_job"


def _system_collection_context(service, collection_id: str) -> Dict[str, Any]:
    """Workspace scan context for scheduled jobs (no grant filtering)."""
    hosts_coll = kv_client.get_collection(service, KV_STIG_HOSTS)
    checklists_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    hosts = kv_client.query_all(hosts_coll, {"stig_collection_id": collection_id})
    checklists = kv_client.query_all(
        checklists_coll, {"stig_collection_id": collection_id}
    )
    baselines = {}
    baseline_ids = {c.get("baseline_id") for c in checklists if c.get("baseline_id")}
    for bid in baseline_ids:
        if bid:
            rec = baselines_svc.get_baseline(service, bid)
            if rec:
                baselines[bid] = rec
    rule_meta_index = reporting_svc._rule_meta_index(service, baseline_ids)
    return {
        "checklist_by_id": {c["_key"]: c for c in checklists if c.get("_key")},
        "host_by_id": {h["_key"]: h for h in hosts if h.get("_key")},
        "baselines": baselines,
        "severity_index": reporting_svc._severity_index_from_meta(rule_meta_index),
    }

ACTION_DELETE = "delete"
ACTION_SET_STATUS_SAVED = "set_status_saved"
ACTION_SET_STATUS_SUBMITTED = "set_status_submitted"
ACTION_SET_RESULT_NOT_CHECKED = "set_result_not_checked"
ACTION_SET_RESULT_INFORMATIONAL = "set_result_informational"


def parse_execute_flag(query: Dict[str, Any], body: Dict[str, Any]) -> bool:
    """Default dry-run. Execute when ``confirm`` is truthy or ``dry_run`` is false."""
    if aging_svc._truthy_flag(query.get("confirm")) or aging_svc._truthy_flag(
        body.get("confirm")
    ):
        return True
    for value in (query.get("dry_run"), body.get("dry_run")):
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            return not value
        text = str(value).strip().lower()
        if text in {"0", "false", "no", "off"}:
            return True
        if text in {"1", "true", "yes", "on"}:
            return False
    return False


def review_already_at_action_target(review: Dict[str, Any], action: str) -> bool:
    wf = review_workflow.workflow_state(review)
    status = (review.get("status") or "not_reviewed").strip().lower()
    if action == ACTION_SET_STATUS_SAVED:
        return wf == "draft"
    if action == ACTION_SET_STATUS_SUBMITTED:
        return wf == "submitted"
    if action == ACTION_SET_RESULT_NOT_CHECKED:
        return status == "not_reviewed" and wf == "draft"
    if action == ACTION_SET_RESULT_INFORMATIONAL:
        return status == "informational" and wf == "draft"
    return False


def _workflow_status_epoch(review: Dict[str, Any]) -> float:
    candidates = [
        review.get("submitted_at"),
        review.get("accepted_at"),
        review.get("rejected_at"),
    ]
    best = 0.0
    for raw in candidates:
        try:
            val = float(raw or 0)
        except (TypeError, ValueError):
            val = 0.0
        if val > best:
            best = val
    return best


def review_trigger_epoch(review: Dict[str, Any], trigger_field: str) -> float:
    field = (trigger_field or "touch_ts").strip().lower()
    content_ts = aging_svc.review_last_change_epoch(review)
    status_ts = _workflow_status_epoch(review)
    if field == "ts":
        return content_ts
    if field == "status_ts":
        return status_ts or content_ts
    # touch_ts — latest material or workflow change
    return max(content_ts, status_ts)


def _host_label_ids(host: Dict[str, Any]) -> List[str]:
    raw = host.get("label_ids")
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    parsed = parse_json_field(raw, default=[]) or []
    if isinstance(parsed, list):
        return [str(x) for x in parsed if x]
    return []


def rule_matches_target(
    rule: Dict[str, Any],
    *,
    checklist: Dict[str, Any],
    host: Dict[str, Any],
) -> bool:
    target = rule.get("target") if isinstance(rule.get("target"), dict) else {}
    ttype = (target.get("type") or "collection").strip().lower()
    host_id = (checklist.get("host_id") or "").strip()
    baseline_id = (checklist.get("baseline_id") or "").strip()
    if ttype in ("collection", ""):
        return True
    if ttype == "asset":
        want = (target.get("host_id") or "").strip()
        return bool(want) and host_id == want
    if ttype == "asset_stig":
        want_host = (target.get("host_id") or "").strip()
        want_base = (target.get("baseline_id") or "").strip()
        return host_id == want_host and baseline_id == want_base
    if ttype == "stig":
        want_base = (target.get("baseline_id") or "").strip()
        return bool(want_base) and baseline_id == want_base
    if ttype == "label":
        want_label = (target.get("label_id") or "").strip()
        return bool(want_label) and want_label in _host_label_ids(host)
    if ttype == "label_stig":
        want_label = (target.get("label_id") or "").strip()
        want_base = (target.get("baseline_id") or "").strip()
        return (
            bool(want_label)
            and bool(want_base)
            and want_label in _host_label_ids(host)
            and baseline_id == want_base
        )
    return False


def review_eligible_for_rule(
    review: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    severity: str,
    now: float,
    checklist: Dict[str, Any],
    host: Dict[str, Any],
) -> bool:
    if not rule.get("enabled"):
        return False
    if not rule_matches_target(rule, checklist=checklist, host=host):
        return False
    filters = {
        "statuses": rule.get("statuses") or aging_svc.DEFAULT_STATUSES,
        "workflow_states": rule.get("workflow_states") or list(aging_svc.DEFAULT_WORKFLOW_STATES),
        "severities": rule.get("severities") or [],
    }
    if not aging_svc.review_matches_aging_filters(review, filters, severity):
        return False
    trigger_ts = review_trigger_epoch(review, rule.get("trigger_field") or "touch_ts")
    if trigger_ts <= 0:
        return False
    threshold = aging_svc.rule_interval_seconds(rule)
    cutoff = now - threshold
    return trigger_ts < cutoff


def _planned_change(
    review: Dict[str, Any],
    rule: Dict[str, Any],
    *,
    checklist: Dict[str, Any],
    host: Dict[str, Any],
    baseline: Dict[str, Any],
    severity: str,
) -> Dict[str, Any]:
    action = rule.get("action") or ""
    row = aging_svc._stale_row(
        review,
        checklist=checklist,
        host=host,
        baseline=baseline,
        severity=severity,
        config={"stale_after_days": 90},
        now=aging_svc.now_epoch(),
    )
    row["aging_rule_id"] = rule.get("id")
    row["aging_action"] = action
    row["aging_trigger_field"] = rule.get("trigger_field")
    row["aging_interval_seconds"] = aging_svc.rule_interval_seconds(rule)
    row["skipped_already_at_target"] = review_already_at_action_target(review, action)
    return row


def _apply_update_action(
    service,
    review: Dict[str, Any],
    action: str,
    username: str,
) -> Dict[str, Any]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    key = review.get("_key")
    if not key:
        raise ValueError("review missing _key")
    existing = kv_client.get_by_key(coll, key) or review
    patch = dict(existing)
    ts = now_epoch()
    patch["updated_at"] = ts
    patch["updated_by"] = username
    if action == ACTION_SET_STATUS_SAVED:
        patch["workflow_state"] = "draft"
    elif action == ACTION_SET_STATUS_SUBMITTED:
        patch["workflow_state"] = "submitted"
        patch["submitted_at"] = ts
        patch["submitted_by"] = username
    elif action == ACTION_SET_RESULT_NOT_CHECKED:
        patch["status"] = "not_reviewed"
        patch["workflow_state"] = "draft"
    elif action == ACTION_SET_RESULT_INFORMATIONAL:
        patch["status"] = "informational"
        patch["workflow_state"] = "draft"
    else:
        raise ValueError(f"unsupported update action: {action}")
    stored = kv_client.update_record(coll, key, kv_record(patch))
    audit.log_event(
        "review_aging",
        "stig_review",
        key,
        username,
        {
            "aging_action": action,
            "rule_action": action,
            "previous_status": existing.get("status"),
            "new_status": stored.get("status"),
            "previous_workflow_state": review_workflow.workflow_state(existing),
            "new_workflow_state": review_workflow.workflow_state(stored),
        },
    )
    review_history_svc.record_review_change(
        service, existing, stored, username, action="update"
    )
    return stored


def _apply_delete(
    service,
    review: Dict[str, Any],
    username: str,
) -> None:
    key = (review.get("_key") or "").strip()
    if not key:
        raise ValueError("review missing _key")
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    history_coll = kv_client.get_collection(service, KV_STIG_REVIEW_HISTORY)
    existing = kv_client.get_by_key(reviews_coll, key)
    if not existing:
        return
    removed_history = 0
    for row in kv_client.query_all(history_coll, {"review_id": key}):
        hist_key = row.get("_key")
        if hist_key:
            kv_client.delete_record(history_coll, hist_key)
            removed_history += 1
    kv_client.delete_record(reviews_coll, key)
    audit.log_event(
        "review_aging_delete",
        "stig_review",
        key,
        username,
        {
            "aging_action": ACTION_DELETE,
            "history_rows_removed": removed_history,
            "checklist_id": existing.get("checklist_id"),
            "rule_id": existing.get("rule_id"),
            "group_id": existing.get("group_id"),
        },
    )


def apply_matched_review(
    service,
    review: Dict[str, Any],
    rule: Dict[str, Any],
    username: str,
    *,
    execute: bool,
) -> Dict[str, Any]:
    action = (rule.get("action") or "").strip().lower()
    key = review.get("_key")
    if review_already_at_action_target(review, action):
        return {
            "review_id": key,
            "rule_id": rule.get("id"),
            "action": action,
            "applied": False,
            "skipped": True,
            "reason": "already_at_target",
        }
    if not execute:
        return {
            "review_id": key,
            "rule_id": rule.get("id"),
            "action": action,
            "applied": False,
            "dry_run": True,
        }
    if action == ACTION_DELETE:
        _apply_delete(service, review, username)
        return {
            "review_id": key,
            "rule_id": rule.get("id"),
            "action": action,
            "applied": True,
            "deleted": True,
        }
    if action in {
        ACTION_SET_STATUS_SAVED,
        ACTION_SET_STATUS_SUBMITTED,
        ACTION_SET_RESULT_NOT_CHECKED,
        ACTION_SET_RESULT_INFORMATIONAL,
    }:
        stored = _apply_update_action(service, review, action, username)
        return {
            "review_id": key,
            "rule_id": rule.get("id"),
            "action": action,
            "applied": True,
            "workflow_state": review_workflow.workflow_state(stored),
            "status": stored.get("status"),
        }
    raise ValueError(f"unknown aging action: {action}")


def _sorted_rules(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = config.get("rules") if isinstance(config.get("rules"), list) else []
    return sorted(rules, key=lambda r: int(r.get("ordinal") or 0))


def apply_collection_rules(
    service,
    collection_id: str,
    username: str,
    session: Dict[str, Any],
    *,
    execute: bool,
    limit: int = 500,
    system_job: bool = False,
) -> Dict[str, Any]:
    if not system_job:
        aging_svc._require_write(service, collection_id, session)
    rec = collections_svc.get_collection(service, collection_id)
    if not rec:
        raise KeyError(collection_id)
    config = aging_svc.parse_config_from_collection(rec)
    rules = [r for r in _sorted_rules(config) if r.get("enabled")]
    now = aging_svc.now_epoch()
    if not rules:
        return {
            "stig_collection_id": collection_id,
            "dry_run": not execute,
            "execute": execute,
            "rules_enabled": 0,
            "matched_count": 0,
            "acted_count": 0,
            "items": [],
            "note": "No enabled review aging rules configured for this workspace.",
        }

    if system_job:
        ctx = _system_collection_context(service, collection_id)
    else:
        ctx = reporting_svc._collection_workspace_context(
            service, collection_id, session
        )
    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    planned: List[Dict[str, Any]] = []
    outcomes: List[Dict[str, Any]] = []
    matched_count = 0
    acted_count = 0

    for rule in rules:
        for checklist_id, checklist in ctx["checklist_by_id"].items():
            host = ctx["host_by_id"].get(checklist.get("host_id") or "", {})
            baseline = ctx["baselines"].get(checklist.get("baseline_id") or "", {})
            for review in kv_client.query_all(reviews_coll, {"checklist_id": checklist_id}):
                sev = reporting_svc.review_severity(review, ctx["severity_index"])
                if not review_eligible_for_rule(
                    review,
                    rule,
                    severity=sev,
                    now=now,
                    checklist=checklist,
                    host=host,
                ):
                    continue
                matched_count += 1
                if len(planned) < limit:
                    planned.append(
                        _planned_change(
                            review,
                            rule,
                            checklist=checklist,
                            host=host,
                            baseline=baseline,
                            severity=sev,
                        )
                    )
                outcome = apply_matched_review(
                    service, review, rule, username, execute=execute
                )
                if outcome.get("applied"):
                    acted_count += 1
                if len(outcomes) < limit:
                    outcomes.append(outcome)

    return {
        "stig_collection_id": collection_id,
        "dry_run": not execute,
        "execute": execute,
        "rules_enabled": len(rules),
        "matched_count": matched_count,
        "acted_count": acted_count,
        "limit": limit,
        "truncated": matched_count > len(planned),
        "planned": planned,
        "results": outcomes,
        "generated_at": now,
    }


def apply_all_workspaces(
    service,
    username: str,
    session: Dict[str, Any],
    *,
    execute: bool,
    limit_per_workspace: int = 500,
) -> Dict[str, Any]:
    if not aging_svc.is_review_aging_job_enabled(service):
        return {
            "dry_run": not execute,
            "execute": execute,
            "job_enabled": False,
            "workspaces_scanned": 0,
            "matched_count": 0,
            "acted_count": 0,
            "collections": [],
            "note": (
                "Review aging job is disabled. Enable via "
                "PATCH /stig_settings/review_aging_job (stig_admin)."
            ),
        }
    now = aging_svc.now_epoch()
    total_matched = 0
    total_acted = 0
    chunks: List[Dict[str, Any]] = []
    scanned = 0
    for collection in collections_svc.list_all_collections(service):
        collection_id = collection.get("_key")
        if not collection_id:
            continue
        config = aging_svc.parse_config_from_collection(collection)
        if not any(r.get("enabled") for r in _sorted_rules(config)):
            continue
        scanned += 1
        chunk = apply_collection_rules(
            service,
            collection_id,
            username or AGING_ACTOR,
            session,
            execute=execute,
            limit=limit_per_workspace,
            system_job=True,
        )
        total_matched += int(chunk.get("matched_count") or 0)
        total_acted += int(chunk.get("acted_count") or 0)
        chunks.append(
            {
                "stig_collection_id": collection_id,
                "collection_name": collection.get("name") or "",
                "matched_count": chunk.get("matched_count"),
                "acted_count": chunk.get("acted_count"),
                "rules_enabled": chunk.get("rules_enabled"),
            }
        )
    aging_svc.record_review_aging_job_run(
        service,
        username,
        {
            "execute": execute,
            "workspaces_scanned": scanned,
            "matched_count": total_matched,
            "acted_count": total_acted,
            "generated_at": now,
        },
    )
    return {
        "dry_run": not execute,
        "execute": execute,
        "job_enabled": True,
        "workspaces_scanned": scanned,
        "matched_count": total_matched,
        "acted_count": total_acted,
        "generated_at": now,
        "collections": chunks,
    }
