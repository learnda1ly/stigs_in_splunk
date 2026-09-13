"""Validate a CKLB document against the STIG Viewer shape."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union

from models import STATUS_TO_CKLB

DOC_KEYS = [
    "title",
    "id",
    "stigs",
    "active",
    "mode",
    "has_path",
    "target_data",
    "cklb_version",
]
TARGET_KEYS = [
    "target_type",
    "host_name",
    "ip_address",
    "mac_address",
    "fqdn",
    "comments",
    "role",
    "is_web_database",
    "technology_area",
    "web_db_site",
    "web_db_instance",
    "classification",
]
STIG_KEYS = [
    "stig_name",
    "display_name",
    "stig_id",
    "release_info",
    "version",
    "uuid",
    "reference_identifier",
    "size",
    "rules",
]
RULE_KEYS = [
    "group_id_src",
    "group_tree",
    "group_id",
    "severity",
    "group_title",
    "rule_id_src",
    "rule_id",
    "rule_version",
    "rule_title",
    "fix_text",
    "weight",
    "check_content",
    "check_content_ref",
    "classification",
    "discussion",
    "false_positives",
    "false_negatives",
    "documentable",
    "security_override_guidance",
    "potential_impacts",
    "third_party_tools",
    "ia_controls",
    "responsibility",
    "mitigations",
    "mitigation_control",
    "legacy_ids",
    "ccis",
    "reference_identifier",
    "uuid",
    "stig_uuid",
    "status",
    "overrides",
    "comments",
    "finding_details",
    "srg_id",
]
EXTRA_RULE_KEYS = {"package_id"}
STATUSES = set(STATUS_TO_CKLB.values()) | set(STATUS_TO_CKLB)
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
GROUP_RE = re.compile(r"^V-\d+")
SV_RE = re.compile(r"^SV-\d+")


@dataclass
class CklbCheckResult:
    path: str
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rule_count: int = 0

    def add(self, message: str, warning: bool = False) -> None:
        if warning:
            self.warnings.append(message)
        else:
            self.errors.append(message)
            self.ok = False


def _is_uuid(value: Any) -> bool:
    text = str(value or "")
    if not UUID_RE.match(text):
        return False
    try:
        uuid.UUID(text)
        return True
    except ValueError:
        return False


def _expect_keys(result: CklbCheckResult, where: str, actual: Any, expected: List[str]) -> None:
    if not isinstance(actual, dict):
        result.add(f"{where}: expected object, got {type(actual).__name__}")
        return
    keys = list(actual.keys())
    missing = [k for k in expected if k not in actual]
    if missing:
        result.add(f"{where}: missing keys {missing}")
    extra = [k for k in keys if k not in expected and k not in EXTRA_RULE_KEYS]
    if extra and where.endswith("rule"):
        extra = [k for k in extra if k not in EXTRA_RULE_KEYS]
    if extra:
        result.add(f"{where}: unexpected keys {extra}", warning=True)
    prefix = [k for k in keys if k in expected]
    if prefix[: len(expected)] != expected and not missing:
        result.add(f"{where}: key order is not STIG Viewer order")


def validate_cklb_doc(doc: Any, path: str = "<memory>", strict: bool = False) -> CklbCheckResult:
    result = CklbCheckResult(path=path, ok=True)
    if not isinstance(doc, dict):
        result.add("document is not a JSON object")
        return result

    _expect_keys(result, "document", doc, DOC_KEYS)
    if doc.get("cklb_version") != "1.0":
        result.add(f"cklb_version should be '1.0', got {doc.get('cklb_version')!r}")
    if doc.get("mode") != 2:
        result.add(f"mode should be 2 (STIG Viewer), got {doc.get('mode')!r}")
    if doc.get("active") is not True:
        result.add("active should be true")
    if doc.get("has_path") is not False:
        result.add("has_path should be false")
    if not _is_uuid(doc.get("id")):
        result.add(f"id should be a UUID, got {doc.get('id')!r}")
    if not str(doc.get("title") or "").strip():
        result.add("title is empty")

    _expect_keys(result, "target_data", doc.get("target_data"), TARGET_KEYS)
    target = doc.get("target_data") if isinstance(doc.get("target_data"), dict) else {}
    if target and not isinstance(target.get("is_web_database"), bool):
        result.add("target_data.is_web_database should be a boolean")

    stigs = doc.get("stigs")
    if not isinstance(stigs, list) or not stigs:
        result.add("stigs must be a non-empty array")
        return result

    for si, stig in enumerate(stigs):
        where = f"stigs[{si}]"
        _expect_keys(result, where, stig, STIG_KEYS)
        if not isinstance(stig, dict):
            continue
        if not _is_uuid(stig.get("uuid")):
            result.add(f"{where}.uuid should be a UUID, got {stig.get('uuid')!r}")
        stig_id = str(stig.get("stig_id") or "")
        if not stig_id or stig_id == "STIG":
            result.add(f"{where}.stig_id looks truncated ({stig_id!r})")
        rules = stig.get("rules")
        if not isinstance(rules, list):
            result.add(f"{where}.rules must be an array")
            continue
        result.rule_count += len(rules)
        if stig.get("size") != len(rules):
            result.add(f"{where}.size is {stig.get('size')}, but rules has {len(rules)}")
        for ri, rule in enumerate(rules):
            _validate_rule(result, f"{where}.rules[{ri}]", rule, stig, strict)

    return result


def _validate_rule(
    result: CklbCheckResult,
    where: str,
    rule: Any,
    stig: Dict[str, Any],
    strict: bool,
) -> None:
    _expect_keys(result, where, rule, RULE_KEYS)
    if not isinstance(rule, dict):
        return
    gid = str(rule.get("group_id") or "")
    if not GROUP_RE.match(gid):
        result.add(f"{where}.group_id should look like V-nnnnnn, got {gid!r}")
    if rule.get("group_id_src") != gid:
        result.add(f"{where}.group_id_src should match group_id")
    rid = str(rule.get("rule_id") or "")
    if rid.endswith("_rule"):
        result.add(f"{where}.rule_id should not end with _rule, got {rid!r}")
    if not SV_RE.match(rid):
        result.add(f"{where}.rule_id should look like SV-…, got {rid!r}")
    discussion = str(rule.get("discussion") or "")
    if "<VulnDiscussion>" in discussion:
        result.add(f"{where}.discussion still has DISA XML wrappers")
    status = rule.get("status")
    if status not in STATUSES:
        result.add(f"{where}.status is not a CKLB status: {status!r}")
    if not isinstance(rule.get("group_tree"), list) or not rule.get("group_tree"):
        result.add(f"{where}.group_tree should be a non-empty array")
    cref = rule.get("check_content_ref")
    if not isinstance(cref, dict) or not cref.get("href"):
        result.add(f"{where}.check_content_ref should be {{href, name}}")
    if not isinstance(rule.get("ccis"), list):
        result.add(f"{where}.ccis should be an array")
    if not isinstance(rule.get("legacy_ids"), list):
        result.add(f"{where}.legacy_ids should be an array")
    if not isinstance(rule.get("overrides"), dict):
        result.add(f"{where}.overrides should be an object")
    if not _is_uuid(rule.get("uuid")):
        result.add(f"{where}.uuid should be a UUID")
    if rule.get("stig_uuid") != stig.get("uuid"):
        result.add(f"{where}.stig_uuid should match parent stig.uuid")
    if not isinstance(rule.get("documentable"), str):
        result.add(f"{where}.documentable should be a string")
    if strict:
        if not str(rule.get("srg_id") or "").startswith("SRG-"):
            result.add(f"{where}.srg_id is missing")
        if not str(rule.get("reference_identifier") or "").strip():
            result.add(f"{where}.reference_identifier is empty")
    elif not str(rule.get("srg_id") or "").strip():
        result.add(f"{where}.srg_id is empty", warning=True)


def validate_cklb_file(path: Union[str, Path], strict: bool = False) -> CklbCheckResult:
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        result = CklbCheckResult(path=str(file_path), ok=False)
        result.add(f"cannot read file: {exc}")
        return result
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        result = CklbCheckResult(path=str(file_path), ok=False)
        result.add(f"invalid JSON: {exc}")
        return result
    return validate_cklb_doc(doc, path=str(file_path), strict=strict)


def validate_paths(paths: Iterable[Union[str, Path]], strict: bool = False) -> List[CklbCheckResult]:
    return [validate_cklb_file(path, strict=strict) for path in paths]


def format_result(result: CklbCheckResult, verbose: bool = False, limit: int = 20) -> str:
    status = "OK" if result.ok else "FAIL"
    lines = [f"{status}  {result.path}  ({result.rule_count} rules)"]
    errors = result.errors if verbose else result.errors[:limit]
    warns = result.warnings if verbose else result.warnings[:limit]
    for err in errors:
        lines.append(f"  error: {err}")
    hidden_err = 0 if verbose else max(0, len(result.errors) - limit)
    if hidden_err:
        lines.append(f"  error: … {hidden_err} more (re-run with --verbose)")
    for warn in warns:
        lines.append(f"  warn:  {warn}")
    hidden_warn = 0 if verbose else max(0, len(result.warnings) - limit)
    if hidden_warn:
        lines.append(f"  warn:  … {hidden_warn} more (re-run with --verbose)")
    return "\n".join(lines)
