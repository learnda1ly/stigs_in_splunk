"""Access control for stig_collection-scoped data (grants + legacy principals)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set

ADMIN_ROLES = frozenset({"admin", "sc_admin"})

GRANT_ROLES = frozenset({"owner", "manager", "member", "restricted"})
ROLE_RANK = {"restricted": 0, "member": 1, "manager": 2, "owner": 3}

# Maps grant roles to allowed REST/UI capabilities (see spec.md § ACL).
GRANT_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "owner": {
        "read": True,
        "write": True,
        "manage_grants": True,
        "edit_collection": True,
        "edit_access_principals": True,
    },
    "manager": {
        "read": True,
        "write": True,
        "manage_grants": True,
        "edit_collection": True,
        "edit_access_principals": False,
    },
    "member": {
        "read": True,
        "write": False,  # requires stig_write capability
        "manage_grants": False,
        "edit_collection": False,
        "edit_access_principals": False,
    },
    "restricted": {
        "read": True,
        "write": False,  # requires stig_write + ACL scope
        "manage_grants": False,
        "edit_collection": False,
        "edit_access_principals": False,
    },
}


@dataclass(frozen=True)
class WorkspaceAccess:
    """Effective workspace access for one user session."""

    can_read: bool
    can_write: bool
    manage_grants: bool
    edit_collection: bool
    edit_access_principals: bool
    grant_role: Optional[str]
    acl_host_ids: Optional[Set[str]]
    acl_baseline_ids: Optional[Set[str]]
    acl_label_ids: Optional[Set[str]]
    admin_bypass: bool = False

    @property
    def acl_scoped(self) -> bool:
        return (
            self.acl_host_ids is not None
            or self.acl_baseline_ids is not None
            or self.acl_label_ids is not None
        )


def parse_access_principals(raw: Any) -> List[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (TypeError, ValueError):
        pass
    return []


def parse_host_label_ids(host_record: Dict[str, Any]) -> Set[str]:
    parsed = _parse_id_set(host_record.get("label_ids"))
    return parsed if parsed is not None else set()


def _parse_id_set(raw: Any) -> Optional[Set[str]]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(raw, list):
        return None
    values = {str(x).strip() for x in raw if str(x).strip()}
    return values if values else None


def user_roles(session: Dict[str, Any]) -> Set[str]:
    roles: Set[str] = set()
    for role in session.get("roles", []) or []:
        roles.add(str(role))
    user = session.get("user")
    if user:
        roles.add(str(user))
    return roles


def user_has_stig_admin(session: Dict[str, Any]) -> bool:
    roles = user_roles(session)
    if roles & ADMIN_ROLES:
        return True
    caps = session.get("capabilities") or {}
    if caps.get("stig_admin"):
        return True
    return "stig_admin" in roles


def user_has_stig_write(session: Dict[str, Any]) -> bool:
    if user_has_stig_admin(session):
        return True
    caps = session.get("capabilities") or {}
    return bool(caps.get("stig_write"))


def _principal_matches(principal: str, username: str, roles: Set[str]) -> bool:
    if principal.startswith("user:") and principal[5:] == username:
        return True
    if principal.startswith("role:") and principal[5:] in roles:
        return True
    return False


def _legacy_principal_access(
    collection_record: Dict[str, Any], session: Dict[str, Any]
) -> bool:
    username = session.get("user") or ""
    roles = user_roles(session)
    principals = parse_access_principals(collection_record.get("access_principals"))
    if not principals:
        return True
    for principal in principals:
        if _principal_matches(principal, username, roles):
            return True
    return False


def _pick_grant(
    grants: Iterable[Dict[str, Any]], session: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    username = session.get("user") or ""
    roles = user_roles(session)
    best: Optional[Dict[str, Any]] = None
    best_rank = -1
    for grant in grants:
        principal = (grant.get("principal") or "").strip()
        if not principal or not _principal_matches(principal, username, roles):
            continue
        role = (grant.get("grant_role") or "member").strip().lower()
        if role not in GRANT_ROLES:
            role = "member"
        rank = ROLE_RANK.get(role, 0)
        if rank > best_rank:
            best_rank = rank
            best = grant
    return best


def resolve_workspace_access(
    collection_record: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]] = None,
) -> WorkspaceAccess:
    """Resolve effective access; grants override legacy principals when present."""
    if user_has_stig_admin(session):
        return WorkspaceAccess(
            can_read=True,
            can_write=True,
            manage_grants=True,
            edit_collection=True,
            edit_access_principals=True,
            grant_role=None,
            acl_host_ids=None,
            acl_baseline_ids=None,
            acl_label_ids=None,
            admin_bypass=True,
        )

    grant = _pick_grant(grants or [], session)
    legacy = _legacy_principal_access(collection_record, session)

    if not grant and not legacy:
        return WorkspaceAccess(
            can_read=False,
            can_write=False,
            manage_grants=False,
            edit_collection=False,
            edit_access_principals=False,
            grant_role=None,
            acl_host_ids=None,
            acl_baseline_ids=None,
            acl_label_ids=None,
        )

    if grant:
        role = (grant.get("grant_role") or "member").strip().lower()
        if role not in GRANT_ROLES:
            role = "member"
        caps = GRANT_CAPABILITIES[role]
        acl_hosts = _parse_id_set(grant.get("acl_host_ids"))
        acl_baselines = _parse_id_set(grant.get("acl_baseline_ids"))
        acl_labels = _parse_id_set(grant.get("acl_labels"))
        can_write = caps["write"] or (
            role in {"member", "restricted"} and user_has_stig_write(session)
        )
        return WorkspaceAccess(
            can_read=caps["read"],
            can_write=can_write,
            manage_grants=caps["manage_grants"],
            edit_collection=caps["edit_collection"],
            edit_access_principals=caps["edit_access_principals"],
            grant_role=role,
            acl_host_ids=acl_hosts,
            acl_baseline_ids=acl_baselines,
            acl_label_ids=acl_labels,
        )

    # Legacy access_principals only — equivalent to member grant (full workspace).
    can_write = user_has_stig_write(session)
    return WorkspaceAccess(
        can_read=True,
        can_write=can_write,
        manage_grants=False,
        edit_collection=False,
        edit_access_principals=False,
        grant_role="member",
        acl_host_ids=None,
        acl_baseline_ids=None,
        acl_label_ids=None,
    )


def user_can_read_collection(
    collection_record: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    return resolve_workspace_access(collection_record, session, grants).can_read


def user_can_write_collection(
    collection_record: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    return resolve_workspace_access(collection_record, session, grants).can_write


def user_can_manage_grants(
    collection_record: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    return resolve_workspace_access(collection_record, session, grants).manage_grants


def user_can_edit_collection(
    collection_record: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    ctx = resolve_workspace_access(collection_record, session, grants)
    return ctx.edit_collection or ctx.edit_access_principals


def host_allowed(host_record: Dict[str, Any], access_ctx: WorkspaceAccess) -> bool:
    if access_ctx.admin_bypass:
        return True
    if access_ctx.acl_host_ids:
        key = host_record.get("_key") or ""
        if key not in access_ctx.acl_host_ids:
            return False
    if access_ctx.acl_label_ids:
        host_labels = parse_host_label_ids(host_record)
        if not host_labels.intersection(access_ctx.acl_label_ids):
            return False
    return True


def checklist_allowed(
    checklist_record: Dict[str, Any],
    access_ctx: WorkspaceAccess,
    host_record: Optional[Dict[str, Any]] = None,
) -> bool:
    """ACL dimensions compose as AND: each non-empty host/baseline/label filter must pass."""
    if access_ctx.admin_bypass:
        return True
    host_id = checklist_record.get("host_id") or ""
    baseline_id = checklist_record.get("baseline_id") or ""
    if access_ctx.acl_host_ids and host_id not in access_ctx.acl_host_ids:
        return False
    if access_ctx.acl_baseline_ids and baseline_id not in access_ctx.acl_baseline_ids:
        return False
    if access_ctx.acl_label_ids:
        if host_record is None:
            return False
        host_labels = parse_host_label_ids(host_record)
        if not host_labels.intersection(access_ctx.acl_label_ids):
            return False
    return True


def filter_hosts(
    records: Iterable[Dict[str, Any]], access_ctx: WorkspaceAccess
) -> List[Dict[str, Any]]:
    return [r for r in records if host_allowed(r, access_ctx)]


def filter_checklists(
    records: Iterable[Dict[str, Any]],
    access_ctx: WorkspaceAccess,
    host_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if access_ctx.acl_label_ids:
        host_by_id = host_by_id or {}
        return [
            r
            for r in records
            if checklist_allowed(
                r, access_ctx, host_by_id.get(r.get("host_id") or "")
            )
        ]
    return [r for r in records if checklist_allowed(r, access_ctx)]


def user_can_accept_reviews(
    collection_record: Dict[str, Any],
    session: Dict[str, Any],
    grants: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Owner/manager accept-reject governance on submitted reviews.

    Accept does not require workspace write. Besides ``stig_admin``, callers need
    read access plus an **owner** or **manager** workspace grant, or a match on
    ``review_accept_principals``. The Splunk ``stig_review_accept`` capability
    does not grant accept on every readable workspace (pair it with explicit
    principals or owner/manager grants per workspace).
    """
    if user_has_stig_admin(session):
        return True
    if not user_can_read_collection(collection_record, session, grants):
        return False
    ctx = resolve_workspace_access(collection_record, session, grants)
    if ctx.grant_role in {"owner", "manager"}:
        return True
    accept_principals = parse_access_principals(
        collection_record.get("review_accept_principals")
    )
    if not accept_principals:
        return False
    username = session.get("user") or ""
    roles = user_roles(session)
    return any(
        _principal_matches(principal, username, roles) for principal in accept_principals
    )


def filter_collections_for_user(
    records: Iterable[Dict[str, Any]],
    session: Dict[str, Any],
    grants_by_collection: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    grants_by_collection = grants_by_collection or {}
    out: List[Dict[str, Any]] = []
    for rec in records:
        cid = rec.get("_key") or ""
        grants = grants_by_collection.get(cid, [])
        if user_can_read_collection(rec, session, grants):
            out.append(rec)
    return out
