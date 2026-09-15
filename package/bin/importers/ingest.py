"""STIG Manager Watcher-shaped checklist ingest.

ParseResult matches reviewsFromCkl / reviewsFromCklb from
stig-manager-client-modules so streamed findings can be posted the same way
Watcher posts reviews to a Collection.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from models import RESULT_TO_STATUS, STATUS_TO_RESULT, normalize_status

EMPTY_STATS = {
    "pass": 0,
    "fail": 0,
    "notapplicable": 0,
    "notchecked": 0,
    "notselected": 0,
    "informational": 0,
    "error": 0,
    "fixed": 0,
    "unknown": 0,
}

MAX_COMMENT_LENGTH = 32767
MAX_NAME_LENGTH = 255


def detect_format(source_uri: str = "", content: bytes | str = b"") -> str:
    name = (source_uri or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if name.endswith(".cklb"):
        return "cklb"
    if name.endswith(".ckl"):
        return "ckl"
    if isinstance(content, bytes):
        sample = content.lstrip()[:32]
        if sample.startswith(b"{") or sample.startswith(b"["):
            return "cklb"
        return "ckl"
    text = str(content).lstrip()
    if text.startswith("{") or text.startswith("["):
        return "cklb"
    return "ckl"


def truncate(value: Any, max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if not text:
        return ""
    return text[:max_len] if len(text) > max_len else text


def revision_str(version: Any, release_info: Any) -> Optional[str]:
    ver = None
    if version is not None and str(version).strip():
        match = re.search(r"(\d+)", str(version))
        ver = match.group(1) if match else str(version).strip()
    release = None
    info = str(release_info or "")
    match = re.search(r"Release:\s*(.+?)(?:\s|$)", info)
    if match:
        release = match.group(1).strip()
    if ver and release:
        return f"V{ver}R{release}"
    return None


def empty_stats() -> Dict[str, int]:
    return dict(EMPTY_STATS)


def tally_result(stats: Dict[str, int], result: Optional[str]) -> None:
    key = result or "unknown"
    if key not in stats:
        stats["unknown"] = stats.get("unknown", 0) + 1
        return
    stats[key] += 1


def result_from_status(status: Optional[str], source: str = "internal") -> Optional[str]:
    internal = normalize_status(status, source=source) or normalize_status(status)
    if not internal:
        return None
    return STATUS_TO_RESULT.get(internal)


def status_from_result(result: Optional[str]) -> str:
    if not result:
        return "not_reviewed"
    return RESULT_TO_STATUS.get(str(result).lower()) or normalize_status(result) or "not_reviewed"


def streamed_review(
    *,
    rule_id: str,
    result: str,
    detail: Any = "",
    comment: Any = "",
    status: Optional[str] = "saved",
    result_engine: Any = None,
    group_id: str = "",
) -> Dict[str, Any]:
    """One Watcher/STIG Manager POST-review object."""
    review: Dict[str, Any] = {
        "ruleId": truncate(rule_id, 45) or "",
        "result": result,
        "detail": truncate(detail, MAX_COMMENT_LENGTH) or "",
        "comment": truncate(comment, MAX_COMMENT_LENGTH) or "",
        "resultEngine": result_engine,
    }
    if group_id:
        review["groupId"] = group_id
    if status:
        review["status"] = status
    return review


def streamed_finding(
    review: Dict[str, Any],
    *,
    asset_name: str,
    benchmark_id: str,
    revision: Optional[str],
    collection_id: str,
    source_ref: str = "",
    host_id: str = "",
    checklist_id: str = "",
    baseline_id: str = "",
) -> Dict[str, Any]:
    """Finding event: Watcher review plus the Collection/Asset context."""
    finding = dict(review)
    finding.update(
        {
            "assetName": asset_name,
            "benchmarkId": benchmark_id,
            "revisionStr": revision,
            "collectionId": collection_id,
            "sourceRef": source_ref,
            "hostId": host_id,
            "checklistId": checklist_id,
            "baselineId": baseline_id,
        }
    )
    return finding


def reviews_to_seeds(reviews: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    seeds: Dict[str, Dict[str, str]] = {}
    for review in reviews or []:
        payload = {
            "status": status_from_result(review.get("result")),
            "finding_details": review.get("detail") or "",
            "comments": review.get("comment") or "",
        }
        keys = [review.get("ruleId"), review.get("groupId")]
        extra: List[str] = []
        for key in keys:
            if not key:
                continue
            extra.append(str(key))
            if str(key).endswith("_rule"):
                extra.append(str(key)[: -len("_rule")])
            else:
                extra.append(str(key) + "_rule")
        for key in extra:
            seeds[key] = payload
    return seeds


def match_review_seed(
    rule: Dict[str, Any], seeds: Optional[Dict[str, Dict[str, str]]]
) -> Dict[str, str]:
    if not seeds:
        return {}
    candidates = [
        rule.get("rule_id"),
        rule.get("rule_id_src"),
        rule.get("group_id"),
        rule.get("rule_version"),
    ]
    for key in list(candidates):
        if not key:
            continue
        text = str(key)
        if text.endswith("_rule"):
            candidates.append(text[: -len("_rule")])
        else:
            candidates.append(text + "_rule")
    for key in candidates:
        if key and key in seeds:
            return seeds[key]
    return {}


def parse_ingest(
    format_name: str, body: bytes | str, source_uri: str = ""
) -> Dict[str, Any]:
    fmt = (format_name or detect_format(source_uri, body)).lower()
    if fmt == "ckl":
        from importers import ckl

        return ckl.parse_ckl_ingest(body, source_uri=source_uri)
    if fmt == "cklb":
        from importers import cklb

        return cklb.parse_cklb_ingest(body, source_uri=source_uri)
    raise ValueError(f"unsupported checklist format: {format_name}")
