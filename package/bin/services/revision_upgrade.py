"""Cross-revision checklist upgrade with check_content_hash review merge."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import audit
import kv_client
import review_workflow
import validation
from models import (
    KV_STIG_CHECKLISTS,
    KV_STIG_REVIEWS,
    is_ingest_locked,
    kv_record,
    now_epoch,
)
from services import baselines as baselines_svc
from services import checklists as checklists_svc
from services import grants as grants_svc


_VERSION_RE = re.compile(r"^v?(\d+)\s*r\s*(\d+)$", re.IGNORECASE)


def _stig_id_key(value: Any) -> str:
    return (value or "").strip().casefold()


def _rule_identity(rule: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(rule.get("group_id") or ""),
        str(rule.get("rule_id") or ""),
    )


def match_review_for_rule(
    reviews: List[Dict[str, Any]], rule: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Locate the prior review row for a new baseline rule (composite group_id + rule_id)."""
    gid, rid = _rule_identity(rule)
    if not (gid and rid):
        return None
    for rec in reviews:
        if (
            str(rec.get("group_id") or "") == gid
            and str(rec.get("rule_id") or "") == rid
        ):
            return rec
    return None


def parse_dis_version(version: Any) -> Optional[Tuple[int, int]]:
    text = str(version or "").strip().replace(" ", "")
    if not text:
        return None
    match = _VERSION_RE.match(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def assert_newer_baseline_revision(
    old_baseline: Dict[str, Any], new_baseline: Dict[str, Any]
) -> None:
    """Reject downgrades or ambiguous same-revision picks (explicit upgrade only)."""
    old_ver = parse_dis_version(old_baseline.get("version"))
    new_ver = parse_dis_version(new_baseline.get("version"))
    if old_ver and new_ver:
        if new_ver <= old_ver:
            raise ValueError(
                "target baseline must be a newer revision "
                f"(current {old_baseline.get('version')}, "
                f"requested {new_baseline.get('version')})"
            )
        return
    old_imp = float(old_baseline.get("imported_at") or 0)
    new_imp = float(new_baseline.get("imported_at") or 0)
    if new_imp > old_imp:
        return
    raise ValueError(
        "target baseline must be newer than the checklist baseline "
        "(compare version labels such as V2R7 or import the newer revision later)"
    )


def _governed_row(rec: Dict[str, Any]) -> bool:
    return is_ingest_locked(rec) or not review_workflow.is_editable(rec)


def _merge_review_from_prior(
    prior: Dict[str, Any],
    rule: Dict[str, Any],
    new_baseline_id: str,
    username: str,
    ts: float,
) -> Tuple[Dict[str, Any], str]:
    """Build updated review dict; returns (review, outcome)."""
    new_hash = str(rule.get("check_content_hash") or "")
    old_hash = str(prior.get("check_content_hash") or "")
    hash_match = bool(new_hash and old_hash and new_hash == old_hash)

    patch = dict(prior)
    patch["baseline_id"] = new_baseline_id
    patch["group_id"] = rule.get("group_id")
    patch["rule_id"] = rule.get("rule_id")
    patch["rule_version"] = rule.get("rule_version")
    patch["check_content_hash"] = new_hash
    patch["updated_at"] = ts
    patch["updated_by"] = username

    if hash_match:
        patch["valid"] = validation.persistable_valid(patch)
        return patch, "merged"

    if _governed_row(prior):
        patch["valid"] = validation.persistable_valid(patch)
        return patch, "preserved"

    patch["status"] = "not_reviewed"
    patch["workflow_state"] = review_workflow.DEFAULT_WORKFLOW_STATE
    patch["finding_details"] = ""
    patch["comments"] = ""
    patch["reject_feedback"] = ""
    patch["valid"] = validation.persistable_valid(patch)
    return patch, "reset"


def _blank_review(
    checklist_id: str,
    new_baseline_id: str,
    rule: Dict[str, Any],
    username: str,
    ts: float,
) -> Dict[str, Any]:
    review = {
        "checklist_id": checklist_id,
        "baseline_id": new_baseline_id,
        "group_id": rule.get("group_id"),
        "rule_id": rule.get("rule_id"),
        "rule_version": rule.get("rule_version"),
        "check_content_hash": rule.get("check_content_hash"),
        "status": "not_reviewed",
        "finding_details": "",
        "comments": "",
        "package_id": "",
        "ingest_lock": False,
        "workflow_state": review_workflow.DEFAULT_WORKFLOW_STATE,
        "updated_at": ts,
        "updated_by": username,
    }
    review["valid"] = validation.persistable_valid(review)
    return kv_record(review)


def upgrade_checklist(
    service,
    checklist_id: str,
    new_baseline_id: str,
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """Point checklist at a newer baseline; merge reviews when check hashes match."""
    new_baseline_id = (new_baseline_id or "").strip()
    if not new_baseline_id:
        raise ValueError("baseline_id is required")

    checklist = checklists_svc.get_checklist(service, checklist_id, session, write=True)
    if not checklist:
        raise KeyError(checklist_id)

    old_baseline_id = (checklist.get("baseline_id") or "").strip()
    if old_baseline_id == new_baseline_id:
        raise ValueError("checklist already uses this baseline revision")

    old_baseline = baselines_svc.get_baseline(service, old_baseline_id)
    new_baseline = baselines_svc.get_baseline(service, new_baseline_id)
    if not old_baseline or not new_baseline:
        raise KeyError(new_baseline_id if not new_baseline else old_baseline_id)

    old_stig = _stig_id_key(old_baseline.get("stig_id"))
    new_stig = _stig_id_key(new_baseline.get("stig_id"))
    if not old_stig or old_stig != new_stig:
        raise ValueError(
            "new baseline must be another revision of the same stig_id "
            f"(was {old_baseline.get('stig_id')}, got {new_baseline.get('stig_id')})"
        )

    assert_newer_baseline_revision(old_baseline, new_baseline)

    new_rules = baselines_svc.list_baseline_rules(service, new_baseline_id)
    if not new_rules:
        raise ValueError("target baseline has no rules")

    reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    old_reviews = kv_client.query_all(reviews_coll, {"checklist_id": checklist_id})
    remaining: List[Dict[str, Any]] = list(old_reviews)

    stats = {"merged": 0, "reset": 0, "preserved": 0, "added": 0, "removed": 0}
    ts = now_epoch()
    matched_keys: Set[str] = set()

    for rule in new_rules:
        prior = match_review_for_rule(remaining, rule)
        if prior:
            key = prior.get("_key")
            if key:
                matched_keys.add(str(key))
            updated, outcome = _merge_review_from_prior(
                prior, rule, new_baseline_id, username, ts
            )
            kv_client.update_record(reviews_coll, prior["_key"], kv_record(updated))
            stats[outcome] = stats.get(outcome, 0) + 1
            remaining = [r for r in remaining if r.get("_key") != prior.get("_key")]
            continue

        stored = kv_client.insert_record(
            reviews_coll, _blank_review(checklist_id, new_baseline_id, rule, username, ts)
        )
        stats["added"] += 1
        if stored.get("_key"):
            matched_keys.add(str(stored["_key"]))

    for orphan in old_reviews:
        key = orphan.get("_key")
        if not key or str(key) in matched_keys:
            continue
        kv_client.delete_record(reviews_coll, key)
        stats["removed"] += 1

    checklist_coll = kv_client.get_collection(service, KV_STIG_CHECKLISTS)
    patch = dict(checklist)
    patch["baseline_id"] = new_baseline_id
    patch["updated_at"] = ts
    patch["updated_by"] = username
    stored_checklist = kv_client.update_record(
        checklist_coll, checklist_id, kv_record(patch)
    )

    audit.log_event(
        "upgrade",
        "stig_checklist",
        checklist_id,
        username,
        {
            "from_baseline_id": old_baseline_id,
            "to_baseline_id": new_baseline_id,
            **stats,
        },
    )
    return {
        "checklist": stored_checklist,
        "from_baseline_id": old_baseline_id,
        "to_baseline_id": new_baseline_id,
        **stats,
    }


def upgrade_collection_checklists(
    service,
    collection_id: str,
    new_baseline_id: str,
    username: str,
    session: Dict[str, Any],
    *,
    from_baseline_id: str = "",
    stig_id: str = "",
) -> Dict[str, Any]:
    """Upgrade every checklist in a workspace that matches the source revision."""
    new_baseline_id = (new_baseline_id or "").strip()
    if not new_baseline_id:
        raise ValueError("baseline_id is required")

    new_baseline = baselines_svc.get_baseline(service, new_baseline_id)
    if not new_baseline:
        raise KeyError(new_baseline_id)

    grants_svc.require_workspace_write(service, collection_id, session)

    want_stig = _stig_id_key(stig_id or new_baseline.get("stig_id"))
    from_id = (from_baseline_id or "").strip()

    checklists = checklists_svc.list_checklists(service, session, collection_id)
    targets = []
    for cl in checklists:
        if from_id and (cl.get("baseline_id") or "").strip() != from_id:
            continue
        bl = baselines_svc.get_baseline(service, cl.get("baseline_id") or "")
        if not bl:
            continue
        if _stig_id_key(bl.get("stig_id")) != want_stig:
            continue
        if (cl.get("baseline_id") or "").strip() == new_baseline_id:
            continue
        targets.append(cl)

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for cl in targets:
        key = cl.get("_key")
        if not key:
            continue
        try:
            results.append(
                upgrade_checklist(service, key, new_baseline_id, username, session)
            )
        except (KeyError, ValueError, PermissionError) as exc:
            errors.append({"checklist_id": key, "error": str(exc)})

    return {
        "stig_collection_id": collection_id,
        "to_baseline_id": new_baseline_id,
        "from_baseline_id": from_id or None,
        "stig_id": new_baseline.get("stig_id"),
        "upgraded": len(results),
        "results": results,
        "errors": errors,
    }
