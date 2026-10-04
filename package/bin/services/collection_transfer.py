"""Bulk transfer hosts (assets) and copy review results between workspaces."""

from __future__ import annotations

from typing import Any, Dict, List

import audit
import kv_client
from importers.ingest import reviews_to_seeds
from models import KV_STIG_REVIEWS, STATUS_TO_RESULT
from services import checklists as checklists_svc
from services import collections as collections_svc
from services import grants as grants_svc
from services import hosts as hosts_svc
from services import import_options as import_options_svc

MAX_COPY_RESULTS_HOSTS = 100


def _normalize_host_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _copy_flag(body: Dict[str, Any]) -> bool:
    raw = body.get("copy_results")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    return text in {"1", "true", "yes"}


def _reviews_for_checklist(service, checklist_id: str) -> List[Dict[str, Any]]:
    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    return kv_client.query_all(coll, {"checklist_id": checklist_id})


def _seeds_from_kv_reviews(reviews: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for rec in reviews or []:
        status = rec.get("status") or "not_reviewed"
        result = STATUS_TO_RESULT.get(str(status), "notchecked")
        events.append(
            {
                "ruleId": rec.get("rule_id"),
                "groupId": rec.get("group_id"),
                "result": result,
                "_status": status,
                "detail": rec.get("finding_details") or "",
                "comment": rec.get("comments") or "",
                "resultEngine": rec.get("result_engine"),
            }
        )
    return reviews_to_seeds(events)


def _validate_copy_request(src: str, dst: str, host_ids: List[str]) -> None:
    if not src or not dst:
        raise ValueError("source and destination workspace ids are required")
    if src == dst:
        raise ValueError("source and destination workspace must differ")
    if not host_ids:
        raise ValueError("host_ids required")
    if len(host_ids) > MAX_COPY_RESULTS_HOSTS:
        raise ValueError(
            f"host_ids exceeds maximum of {MAX_COPY_RESULTS_HOSTS} for copy_results"
        )


def copy_results_to_collection(
    service,
    source_collection_id: str,
    dest_collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Copy assessor review fields from source hosts onto same-named hosts in the
    destination workspace. Source hosts are not moved. Matching is by hostname
    (case-insensitive). Checklists are matched by ``baseline_id``; when the
    destination host lacks that assignment, a checklist is created when the
    baseline is usable in the destination workspace.

    Destination ``import_options`` govern workflow resets and empty text merge,
    same as checklist import. Capped at ``MAX_COPY_RESULTS_HOSTS`` assets per
    request.
    """
    src = (source_collection_id or "").strip()
    dst = (dest_collection_id or "").strip()
    host_ids = _normalize_host_ids(body.get("host_ids"))
    _validate_copy_request(src, dst, host_ids)

    if not collections_svc.get_collection(service, src):
        raise KeyError(src)
    if not collections_svc.get_collection(service, dst):
        raise KeyError(dst)

    grants_svc.require_workspace_write(service, src, session)
    grants_svc.require_workspace_write(service, dst, session)

    import_policy = import_options_svc.effective_policy(service, dst, session)

    results: List[Dict[str, Any]] = []
    copied = 0
    failed = 0
    skipped = 0
    reviews_updated = 0

    for host_key in host_ids:
        try:
            source_host = hosts_svc.get_host(service, host_key, session)
            if not source_host:
                raise KeyError(host_key)
            if (source_host.get("stig_collection_id") or "").strip() != src:
                raise ValueError("host_not_in_source_workspace")

            hostname = (source_host.get("hostname") or "").strip()
            dest_host = hosts_svc.find_host_by_hostname(service, session, dst, hostname)
            if not dest_host:
                results.append(
                    {
                        "host_id": host_key,
                        "status": "skipped",
                        "hostname": hostname,
                        "error": "destination_hostname_not_found",
                    }
                )
                skipped += 1
                continue

            dest_host_id = dest_host.get("_key") or ""
            host_reviews_updated = 0
            checklists_copied = 0
            source_checklists = checklists_svc.list_checklists_for_host(
                service, host_key, session
            )
            for source_cl in source_checklists:
                baseline_id = (source_cl.get("baseline_id") or "").strip()
                if not baseline_id:
                    continue
                dest_cl = checklists_svc.find_checklist(
                    service, session, dst, dest_host_id, baseline_id
                )
                if not dest_cl:
                    try:
                        dest_cl, _created = checklists_svc.assign_stig_to_host(
                            service,
                            dest_host_id,
                            {"baseline_id": baseline_id},
                            username,
                            session,
                        )
                    except (KeyError, ValueError, PermissionError):
                        continue

                source_reviews = _reviews_for_checklist(service, source_cl["_key"])
                seeds = _seeds_from_kv_reviews(source_reviews)
                if not seeds:
                    continue
                apply_result = checklists_svc.apply_review_seeds(
                    service,
                    dest_cl["_key"],
                    seeds,
                    username,
                    session,
                    import_policy=import_policy,
                )
                updated = int(apply_result.get("updated") or 0)
                if updated:
                    checklists_copied += 1
                    host_reviews_updated += updated

            if host_reviews_updated > 0:
                audit.log_event(
                    "copy_results",
                    "stig_host",
                    host_key,
                    username,
                    {
                        "from_stig_collection_id": src,
                        "to_stig_collection_id": dst,
                        "destination_host_id": dest_host_id,
                        "reviews_updated": host_reviews_updated,
                    },
                )
                results.append(
                    {
                        "host_id": host_key,
                        "status": "copied",
                        "hostname": hostname,
                        "destination_host_id": dest_host_id,
                        "checklists_copied": checklists_copied,
                        "reviews_updated": host_reviews_updated,
                    }
                )
                copied += 1
                reviews_updated += host_reviews_updated
            else:
                results.append(
                    {
                        "host_id": host_key,
                        "status": "skipped",
                        "hostname": hostname,
                        "destination_host_id": dest_host_id,
                        "error": "no_reviews_copied",
                    }
                )
                skipped += 1
        except KeyError:
            results.append(
                {
                    "host_id": host_key,
                    "status": "error",
                    "error": "not_found",
                }
            )
            failed += 1
        except PermissionError as exc:
            results.append(
                {
                    "host_id": host_key,
                    "status": "error",
                    "error": str(exc) or "forbidden",
                }
            )
            failed += 1
        except ValueError as exc:
            msg = str(exc) or "invalid"
            if msg == "host_not_in_source_workspace":
                results.append(
                    {
                        "host_id": host_key,
                        "status": "skipped",
                        "error": msg,
                    }
                )
                skipped += 1
            else:
                results.append(
                    {
                        "host_id": host_key,
                        "status": "error",
                        "error": msg,
                    }
                )
                failed += 1

    return {
        "from_stig_collection_id": src,
        "to_stig_collection_id": dst,
        "copy_results": True,
        "results": results,
        "summary": {
            "copied": copied,
            "failed": failed,
            "skipped": skipped,
            "reviews_updated": reviews_updated,
        },
    }


def export_hosts_to_collection(
    service,
    source_collection_id: str,
    dest_collection_id: str,
    body: Dict[str, Any],
    username: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Move selected hosts from source to destination workspace.

    Requires workspace write on both sides. Host checklists follow the host;
    reviews remain keyed by checklist_id. ``label_ids`` on each host are kept
    only when the label exists in the destination workspace (same as single-host
    PATCH). Workspace grants are not copied; destination ACL applies after move.

    When ``copy_results`` is true in ``body``, hosts are not moved; use
    :func:`copy_results_to_collection` instead.

    Processing is **per host** with no cross-host transaction: earlier hosts in
    ``host_ids`` remain moved if a later host fails. HTTP **201** is returned
    when ``summary.moved > 0`` even if other rows failed or were skipped.
    """
    if _copy_flag(body):
        return copy_results_to_collection(
            service,
            source_collection_id,
            dest_collection_id,
            body,
            username,
            session,
        )

    src = (source_collection_id or "").strip()
    dst = (dest_collection_id or "").strip()
    if not src or not dst:
        raise ValueError("source and destination workspace ids are required")
    if src == dst:
        raise ValueError("source and destination workspace must differ")

    if not collections_svc.get_collection(service, src):
        raise KeyError(src)
    if not collections_svc.get_collection(service, dst):
        raise KeyError(dst)

    grants_svc.require_workspace_write(service, src, session)
    grants_svc.require_workspace_write(service, dst, session)

    host_ids = _normalize_host_ids(body.get("host_ids"))
    if not host_ids:
        raise ValueError("host_ids required")

    results: List[Dict[str, Any]] = []
    moved = 0
    failed = 0
    skipped = 0

    for host_key in host_ids:
        try:
            rec = hosts_svc.transfer_host_to_collection(
                service,
                host_key,
                src,
                dst,
                username,
                session,
            )
            results.append(
                {
                    "host_id": host_key,
                    "status": "moved",
                    "hostname": rec.get("hostname"),
                    "checklists_moved": rec.get("checklists_moved", 0),
                }
            )
            moved += 1
        except KeyError:
            results.append(
                {
                    "host_id": host_key,
                    "status": "error",
                    "error": "not_found",
                }
            )
            failed += 1
        except PermissionError as exc:
            results.append(
                {
                    "host_id": host_key,
                    "status": "error",
                    "error": str(exc) or "forbidden",
                }
            )
            failed += 1
        except ValueError as exc:
            msg = str(exc) or "invalid"
            if msg == "host_not_in_source_workspace":
                results.append(
                    {
                        "host_id": host_key,
                        "status": "skipped",
                        "error": msg,
                    }
                )
                skipped += 1
            else:
                results.append(
                    {
                        "host_id": host_key,
                        "status": "error",
                        "error": msg,
                    }
                )
                failed += 1

    return {
        "from_stig_collection_id": src,
        "to_stig_collection_id": dst,
        "results": results,
        "summary": {"moved": moved, "failed": failed, "skipped": skipped},
    }
