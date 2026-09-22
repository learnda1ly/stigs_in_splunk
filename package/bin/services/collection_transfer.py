"""Bulk transfer hosts (assets) between workspaces."""

from __future__ import annotations

from typing import Any, Dict, List

from services import collections as collections_svc
from services import grants as grants_svc
from services import hosts as hosts_svc


def _normalize_host_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


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

    Processing is **per host** with no cross-host transaction: earlier hosts in
    ``host_ids`` remain moved if a later host fails. HTTP **201** is returned
    when ``summary.moved > 0`` even if other rows failed or were skipped.
    """
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
