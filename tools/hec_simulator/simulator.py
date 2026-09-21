"""Build Watcher-shaped stig:finding events from XCCDF baselines."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_ROOT = REPO_ROOT / "package" / "bin"
if str(BIN_ROOT) not in sys.path:
    sys.path.insert(0, str(BIN_ROOT))

from importers.events import build_finding_event  # noqa: E402
from importers import ingest  # noqa: E402
from importers import xccdf  # noqa: E402

SOURCE_PRODUCT = "stigman-watcher"
RESULT_CYCLE = ("pass", "fail", "notapplicable", "notchecked")

DEFAULT_MANIFEST = REPO_ROOT / "tests" / "fixtures" / "baselines" / "manifest.yaml"
DEFAULT_HOSTS = Path(__file__).resolve().parent / "hosts.yaml"


def load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML required: pip install pyyaml") from exc
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_baseline_path(manifest_path: Path, entry: Dict[str, Any]) -> Path:
    rel = (entry.get("local_file") or "").strip()
    if not rel:
        raise ValueError("manifest entry missing local_file")
    candidate = (manifest_path.parent / rel).resolve()
    if candidate.is_file():
        return candidate
    flat = manifest_path.parent / Path(rel).name
    if flat.is_file():
        return flat
    raise FileNotFoundError(f"baseline file not found: {candidate}")


def load_baseline(manifest_path: Path, baseline_key: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    data = load_yaml(manifest_path) or {}
    baselines = data.get("baselines") or {}
    entry = baselines.get(baseline_key)
    if not entry:
        raise KeyError(f"unknown baseline key {baseline_key!r} in {manifest_path}")
    path = resolve_baseline_path(manifest_path, entry)
    content = path.read_bytes()
    meta, rules = xccdf.parse_xccdf(content, source_uri=path.name)
    return meta, rules, path.name


def deterministic_result(hostname: str, rule: Dict[str, Any]) -> str:
    rid = rule.get("rule_id") or rule.get("group_id") or rule.get("rule_id_src") or ""
    digest = hashlib.sha256(f"{hostname}|{rid}".encode()).hexdigest()
    idx = int(digest[:8], 16) % len(RESULT_CYCLE)
    return RESULT_CYCLE[idx]


def build_host_events(
    *,
    hostname: str,
    ip: str,
    meta: Dict[str, Any],
    rules: List[Dict[str, Any]],
    source_uri: str,
    collection_id: str,
    collection_name: str = "",
    package_id: str = "",
    collection_id_override: str = "",
) -> List[Dict[str, Any]]:
    coll = (collection_id_override or collection_id or "").strip()
    revision = ingest.revision_str(meta.get("version"), meta.get("release_info"))
    target = {
        "name": hostname,
        "ip": ip,
        "fqdn": f"{hostname}.example.com" if hostname else "",
        "description": f"HEC simulator host {hostname}",
        "metadata": {"cklRole": "None"},
    }
    events: List[Dict[str, Any]] = []
    for rule in rules:
        result = deterministic_result(hostname, rule)
        review = ingest.streamed_review(
            rule_id=str(rule.get("rule_id") or rule.get("rule_id_src") or ""),
            group_id=str(rule.get("group_id") or ""),
            result=result,
            detail=f"Simulated {result} for {hostname}",
            comment="hec_simulator",
            status="saved",
            result_engine={"product": "hec_simulator", "version": "0.1.0"},
        )
        if package_id:
            review["package_id"] = str(package_id)
        event = build_finding_event(
            review,
            rule=rule,
            stig=meta,
            target=target,
            collection_id=coll,
            collection_name=collection_name,
            source_ref=source_uri,
            source_product=SOURCE_PRODUCT,
            revision=revision,
        )
        if package_id:
            event["package_id"] = str(package_id)
        events.append(event)
    return events


def load_hosts_config(path: Path) -> List[Dict[str, Any]]:
    data = load_yaml(path) or {}
    hosts = data.get("hosts")
    if not isinstance(hosts, list):
        raise ValueError(f"hosts config must contain a hosts list: {path}")
    return hosts


def simulate_all_hosts(
    *,
    manifest_path: Path,
    hosts_path: Path,
    collection_id: str,
    collection_name: str = "",
    baseline_key_override: Optional[str] = None,
) -> List[Dict[str, Any]]:
    hosts = load_hosts_config(hosts_path)
    all_events: List[Dict[str, Any]] = []
    for host in hosts:
        key = baseline_key_override or host.get("baseline_key") or host.get("baseline") or "minimal"
        meta, rules, source_uri = load_baseline(manifest_path, str(key))
        hostname = str(host.get("hostname") or host.get("name") or "")
        ip = str(host.get("ip") or host.get("ip_address") or "")
        package_id = str(host.get("package_id") or "")
        host_coll = str(host.get("collection_id") or host.get("collectionId") or "")
        all_events.extend(
            build_host_events(
                hostname=hostname,
                ip=ip,
                meta=meta,
                rules=rules,
                source_uri=source_uri,
                collection_id=collection_id,
                collection_name=collection_name,
                package_id=package_id,
                collection_id_override=host_coll,
            )
        )
    return all_events


def default_collection_id() -> str:
    return (os.environ.get("STIG_COLLECTION_ID") or "").strip()
