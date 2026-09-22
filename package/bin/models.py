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
KV_STIG_COLLECTION_GRANTS = "stig_collection_grants"
KV_STIG_LABELS = "stig_labels"
KV_STIG_HOSTS = "stig_hosts"
KV_STIG_BASELINES = "stig_baselines"
KV_STIG_BASELINE_RULES = "stig_baseline_rules"
KV_STIG_CHECKLISTS = "stig_checklists"
KV_STIG_REVIEWS = "stig_reviews"
KV_STIG_EDITOR_SETTINGS = "stig_editor_settings"
KV_STIG_ASSIGNMENT_RULES = "stig_assignment_rules"
KV_STIG_HOST_BASELINE_ASSIGNMENTS = "stig_host_baseline_assignments"

DEFAULT_INGEST_INDEX = "stig"
DEFAULT_INGEST_SOURCETYPE = "stig:finding"
DEFAULT_HEC_URL = "https://localhost:8088/services/collector/event"
DEFAULT_RECONCILE_EARLIEST = "-15m"

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

# STIG Manager / Watcher streamed review.result values.
STATUS_TO_RESULT = {
    "not_reviewed": "notchecked",
    "open": "fail",
    "not_a_finding": "pass",
    "not_applicable": "notapplicable",
}
RESULT_TO_STATUS = {
    "notchecked": "not_reviewed",
    "notselected": "not_reviewed",
    "unknown": "not_reviewed",
    "error": "not_reviewed",
    "informational": "not_reviewed",
    "fail": "open",
    "fixed": "not_a_finding",
    "pass": "not_a_finding",
    "notapplicable": "not_applicable",
}


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
    if source == "result":
        return RESULT_TO_STATUS.get(key.lower())
    if key in STATUSES:
        return key
    mapped = RESULT_TO_STATUS.get(key.lower())
    if mapped:
        return mapped
    mapped = CKL_TO_STATUS.get(key)
    if mapped:
        return mapped
    mapped = CKLB_TO_STATUS.get(key)
    if mapped:
        return mapped
    return None


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def as_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None


def is_ingest_locked(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return False
    return bool(as_bool(record.get("ingest_lock")))


def kv_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare a dict for KV insert/update (no None values)."""
    out: Dict[str, Any] = {}
    for key, val in record.items():
        if val is None:
            continue
        out[key] = val
    return out
