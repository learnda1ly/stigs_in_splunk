"""Constants and shared helpers for STIG KV entities."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

APP_NAME = "stigs_in_splunk"

KV_STIG_COLLECTIONS = "stig_collections"
KV_STIG_HOSTS = "stig_hosts"
KV_STIG_BASELINES = "stig_baselines"
KV_STIG_BASELINE_RULES = "stig_baseline_rules"
KV_STIG_CHECKLISTS = "stig_checklists"
KV_STIG_REVIEWS = "stig_reviews"

STATUSES = frozenset(
    {"not_reviewed", "open", "not_a_finding", "not_applicable"}
)

STATUS_TO_CKLB = {
    "not_reviewed": "not_reviewed",
    "open": "open",
    "not_a_finding": "not_a_finding",
    "not_applicable": "not_applicable",
}

STATUS_TO_CKL = {
    "not_reviewed": "Not_Reviewed",
    "open": "Open",
    "not_a_finding": "NotAFinding",
    "not_applicable": "Not_Applicable",
}

CKLB_TO_STATUS = {v: k for k, v in STATUS_TO_CKLB.items()}
CKL_TO_STATUS = {v: k for k, v in STATUS_TO_CKL.items()}


def new_id() -> str:
    # Splunk KV _key values must not contain dashes (use 32-char hex).
    return uuid.uuid4().hex


def now_epoch() -> float:
    return time.time()


def normalize_check_content(text: str) -> str:
    if not text:
        return ""
    collapsed = re.sub(r"\s+", " ", text.strip())
    return collapsed


def check_content_hash(text: str) -> str:
    normalized = normalize_check_content(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def baseline_content_fingerprint(
    meta: Dict[str, Any], rules: List[Dict[str, Any]]
) -> str:
    """Stable id for one STIG revision; new revision => new fingerprint."""
    revision = {
        "stig_id": (meta.get("stig_id") or "").strip().casefold(),
        "version": (meta.get("version") or "").strip(),
        "release_info": normalize_check_content(meta.get("release_info") or ""),
        "benchmark_date": (meta.get("benchmark_date") or "").strip(),
        "xccdf_benchmark_id": (meta.get("xccdf_benchmark_id") or "").strip(),
    }
    rule_keys = []
    for rule in sorted(
        rules,
        key=lambda r: (
            (r.get("group_id") or ""),
            (r.get("rule_id") or ""),
            (r.get("rule_version") or ""),
        ),
    ):
        rule_keys.append(
            {
                "group_id": rule.get("group_id") or "",
                "rule_id": rule.get("rule_id") or "",
                "rule_version": rule.get("rule_version") or "",
                "check_content_hash": rule.get("check_content_hash") or "",
            }
        )
    payload = {"revision": revision, "rules": rule_keys}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_json_field(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def dumps_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def normalize_status(value: Optional[str], source: str = "internal") -> Optional[str]:
    if value is None:
        return None
    key = value.strip()
    if source == "cklb":
        return CKLB_TO_STATUS.get(key, key.lower())
    if source == "ckl":
        return CKL_TO_STATUS.get(key)
    if key in STATUSES:
        return key
    return None


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def kv_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare a dict for KV insert/update (no None values)."""
    out: Dict[str, Any] = {}
    for key, val in record.items():
        if val is None:
            continue
        out[key] = val
    return out
