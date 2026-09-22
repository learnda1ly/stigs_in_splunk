"""Cross-asset peer reviews for the same rule within a workspace."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import review_workflow
from models import KV_STIG_REVIEWS
import kv_client
from services import baselines as baselines_svc
from services import checklists as checklists_svc
from services import hosts as hosts_svc
from services import review_history as review_history_svc
from services import reviews as reviews_svc

COPY_FIELDS = ("status", "finding_details", "comments")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _stig_id_for_baseline(service, baseline_id: str) -> str:
    if not baseline_id:
        return ""
    baseline = baselines_svc.get_baseline(service, baseline_id)
    if not baseline:
        return ""
    return _text(baseline.get("stig_id")).casefold()


def _baseline_stig_map(service, baseline_ids: Set[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for bl_id in baseline_ids:
        if not bl_id:
            continue
        out[bl_id] = _stig_id_for_baseline(service, bl_id)
    return out


def _rule_identity_match(anchor: Dict[str, Any], peer: Dict[str, Any]) -> bool:
    anchor_gid = _text(anchor.get("group_id"))
    anchor_rid = _text(anchor.get("rule_id"))
    peer_gid = _text(peer.get("group_id"))
    peer_rid = _text(peer.get("rule_id"))
    if anchor_rid and peer_rid != anchor_rid:
        return False
    if anchor_gid and peer_gid != anchor_gid:
        return False
    if not anchor_rid:
        return False
    anchor_ver = _text(anchor.get("rule_version"))
    peer_ver = _text(peer.get("rule_version"))
    if anchor_ver and peer_ver and anchor_ver != peer_ver:
        return False
    return True


def _peer_checklist_ids(
    service,
    session: Dict[str, Any],
    collection_id: str,
    anchor_checklist_id: str,
    anchor_baseline_id: str,
    anchor_stig_id: str,
) -> Set[str]:
    checklists = checklists_svc.list_checklists(service, session, collection_id)
    baseline_ids = {
        _text(cl.get("baseline_id"))
        for cl in checklists
        if cl.get("baseline_id")
    }
    baseline_ids.add(anchor_baseline_id)
    stig_map = _baseline_stig_map(service, baseline_ids)
    out: Set[str] = set()
    for cl in checklists:
        key = _text(cl.get("_key"))
        if not key or key == anchor_checklist_id:
            continue
        bl_id = _text(cl.get("baseline_id"))
        if anchor_baseline_id and bl_id == anchor_baseline_id:
            out.add(key)
            continue
        peer_stig = stig_map.get(bl_id, "")
        if anchor_stig_id and peer_stig == anchor_stig_id:
            out.add(key)
    return out


def _snippet(text: str, limit: int = 120) -> str:
    cleaned = " ".join(_text(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _public_peer_row(
    service,
    session: Dict[str, Any],
    peer: Dict[str, Any],
    checklist: Dict[str, Any],
) -> Dict[str, Any]:
    host_id = _text(checklist.get("host_id"))
    host = hosts_svc.get_host(service, host_id, session) if host_id else None
    hostname = (host or {}).get("hostname") or host_id or "—"
    details = _text(peer.get("finding_details"))
    comments = _text(peer.get("comments"))
    return {
        "review_id": peer.get("_key") or "",
        "checklist_id": checklist.get("_key") or "",
        "host_id": host_id,
        "hostname": hostname,
        "baseline_id": _text(peer.get("baseline_id") or checklist.get("baseline_id")),
        "status": peer.get("status") or "",
        "workflow_state": review_workflow.workflow_state(peer),
        "finding_details": details,
        "finding_details_snippet": _snippet(details),
        "comments": comments,
        "comments_snippet": _snippet(comments),
        "updated_at": peer.get("updated_at"),
        "updated_by": peer.get("updated_by") or "",
        "valid": peer.get("valid"),
    }


def list_review_peers(
    service,
    review_id: str,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    anchor = review_history_svc._require_visible_review(service, review_id, session)
    checklist_id = _text(anchor.get("checklist_id"))
    checklist = checklists_svc.get_checklist(service, checklist_id, session)
    if not checklist:
        raise KeyError(review_id)
    collection_id = _text(checklist.get("stig_collection_id"))
    anchor_baseline_id = _text(anchor.get("baseline_id") or checklist.get("baseline_id"))
    anchor_stig_id = _stig_id_for_baseline(service, anchor_baseline_id)

    peer_cl_ids = _peer_checklist_ids(
        service,
        session,
        collection_id,
        checklist_id,
        anchor_baseline_id,
        anchor_stig_id,
    )
    if not peer_cl_ids:
        return {
            "review_id": review_id,
            "rule_id": anchor.get("rule_id") or "",
            "group_id": anchor.get("group_id") or "",
            "rule_version": anchor.get("rule_version") or "",
            "stig_collection_id": collection_id,
            "peers": [],
        }

    coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
    query: Dict[str, Any] = {}
    rule_id = _text(anchor.get("rule_id"))
    if rule_id:
        query["rule_id"] = rule_id
    candidates = kv_client.query_all(coll, query if query else None)

    checklist_by_id = {
        _text(cl.get("_key")): cl
        for cl in checklists_svc.list_checklists(service, session, collection_id)
        if cl.get("_key")
    }

    peers: List[Dict[str, Any]] = []
    for rec in candidates:
        if rec.get("_key") == review_id:
            continue
        cl_id = _text(rec.get("checklist_id"))
        if cl_id not in peer_cl_ids:
            continue
        if not _rule_identity_match(anchor, rec):
            continue
        cl = checklist_by_id.get(cl_id)
        if not cl:
            continue
        peers.append(_public_peer_row(service, session, rec, cl))

    peers.sort(
        key=lambda row: (
            _text(row.get("hostname")).lower(),
            _text(row.get("review_id")),
        )
    )
    return {
        "review_id": review_id,
        "rule_id": anchor.get("rule_id") or "",
        "group_id": anchor.get("group_id") or "",
        "rule_version": anchor.get("rule_version") or "",
        "stig_collection_id": collection_id,
        "peers": peers,
    }


def _resolve_peer_review(
    service,
    anchor_id: str,
    peer_review_id: str,
    session: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    listing = list_review_peers(service, anchor_id, session)
    for row in listing.get("peers") or []:
        if _text(row.get("review_id")) == _text(peer_review_id):
            reviews_coll = kv_client.get_collection(service, KV_STIG_REVIEWS)
            peer = kv_client.get_by_key(reviews_coll, peer_review_id)
            if not peer:
                raise KeyError(peer_review_id)
            return listing, peer
    raise KeyError(peer_review_id)


def copy_from_peer(
    service,
    review_id: str,
    peer_review_id: str,
    username: str,
    session: Dict[str, Any],
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    review_history_svc._require_visible_review(service, review_id, session)
    _listing, peer = _resolve_peer_review(service, review_id, peer_review_id, session)

    body = body or {}
    fields = body.get("fields")
    if fields is None:
        copy_keys = list(COPY_FIELDS)
    elif isinstance(fields, list):
        copy_keys = [str(f) for f in fields if str(f) in COPY_FIELDS]
        if not copy_keys:
            raise ValueError("fields must include at least one of: status, finding_details, comments")
    else:
        raise ValueError("fields must be an array when provided")

    patch = {key: peer.get(key) for key in copy_keys}
    try:
        updated = reviews_svc.update_review(service, review_id, patch, username, session)
    except PermissionError:
        raise
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "review": updated,
        "copied_from": peer_review_id,
        "copied_fields": copy_keys,
    }
