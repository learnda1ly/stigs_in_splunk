"""Read-only comparison of two baseline revisions (library browse)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from models import parse_json_field
from services import baselines as baselines_svc
from services.baseline_library import revision_summary
from services.revision_upgrade import _rule_identity, _stig_id_key

# Fields included in revision compare reports (rule identity is matched separately).
COMPARE_FIELDS: Tuple[str, ...] = (
    "rule_title",
    "severity",
    "rule_version",
    "group_title",
    "check_content",
    "fix_text",
    "discussion",
    "check_content_hash",
    "ccis",
)


def _normalize_field(rule: Dict[str, Any], field: str) -> str:
    raw = rule.get(field)
    if field == "ccis":
        parsed = parse_json_field(raw, default=[]) or []
        if not isinstance(parsed, list):
            parsed = []
        return json.dumps(sorted(str(c) for c in parsed), sort_keys=True)
    return str(raw or "").strip()


def _rule_summary(rule: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rule_key": rule.get("_key") or "",
        "group_id": rule.get("group_id") or "",
        "rule_id": rule.get("rule_id") or "",
        "rule_version": rule.get("rule_version") or "",
        "rule_title": rule.get("rule_title") or "",
        "severity": rule.get("severity") or "",
        "check_content_hash": rule.get("check_content_hash") or "",
    }


def _diff_fields(
    from_rule: Dict[str, Any], to_rule: Dict[str, Any]
) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    changed_names: List[str] = []
    details: Dict[str, Dict[str, str]] = {}
    for field in COMPARE_FIELDS:
        old_val = _normalize_field(from_rule, field)
        new_val = _normalize_field(to_rule, field)
        if old_val != new_val:
            changed_names.append(field)
            details[field] = {"from": old_val, "to": new_val}
    return changed_names, details


def _index_rules(rules: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for rule in rules:
        key = _rule_identity(rule)
        if not (key[0] and key[1]):
            continue
        out[key] = rule
    return out


def compare_baselines(
    service,
    from_baseline_id: str,
    to_baseline_id: str,
) -> Dict[str, Any]:
    """Compare two revisions of the same STIG (read-only rule/field report)."""
    from_id = (from_baseline_id or "").strip()
    to_id = (to_baseline_id or "").strip()
    if not from_id or not to_id:
        raise ValueError("from_baseline_id and to_baseline_id are required")
    if from_id == to_id:
        raise ValueError("choose two different baseline revisions")

    from_baseline = baselines_svc.get_baseline(service, from_id)
    to_baseline = baselines_svc.get_baseline(service, to_id)
    if not from_baseline or not to_baseline:
        raise KeyError(from_id if not from_baseline else to_id)

    from_stig = _stig_id_key(from_baseline.get("stig_id"))
    to_stig = _stig_id_key(to_baseline.get("stig_id"))
    if not from_stig or from_stig != to_stig:
        raise ValueError(
            "baselines must be revisions of the same stig_id "
            f"(from {from_baseline.get('stig_id')}, to {to_baseline.get('stig_id')})"
        )

    from_rules = _index_rules(baselines_svc.list_baseline_rules(service, from_id))
    to_rules = _index_rules(baselines_svc.list_baseline_rules(service, to_id))

    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    unchanged_count = 0

    for identity, to_rule in sorted(to_rules.items(), key=lambda item: item[0]):
        from_rule = from_rules.get(identity)
        if not from_rule:
            added.append(_rule_summary(to_rule))
            continue
        field_names, field_diff = _diff_fields(from_rule, to_rule)
        if not field_names:
            unchanged_count += 1
            continue
        hash_changed = "check_content_hash" in field_names
        changed.append(
            {
                **_rule_summary(to_rule),
                "from_rule_key": from_rule.get("_key") or "",
                "to_rule_key": to_rule.get("_key") or "",
                "changed_fields": field_names,
                "check_content_hash_changed": hash_changed,
                "review_would_carry_forward": not hash_changed,
                "fields": field_diff,
            }
        )

    for identity, from_rule in sorted(from_rules.items(), key=lambda item: item[0]):
        if identity not in to_rules:
            removed.append(_rule_summary(from_rule))

    return {
        "stig_id": from_baseline.get("stig_id") or "",
        "from_baseline": revision_summary(from_baseline),
        "to_baseline": revision_summary(to_baseline),
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": unchanged_count,
            "from_rule_count": len(from_rules),
            "to_rule_count": len(to_rules),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }
