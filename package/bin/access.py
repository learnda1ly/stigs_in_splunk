"""Access control for stig_collection-scoped data."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Set

ADMIN_ROLES = frozenset({"admin", "sc_admin"})


def _parse_principals(raw: Any) -> List[str]:
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


def user_can_read_collection(
    collection_record: Dict[str, Any], session: Dict[str, Any]
) -> bool:
    if user_has_stig_admin(session):
        return True
    username = session.get("user") or ""
    roles = user_roles(session)
    principals = _parse_principals(collection_record.get("access_principals"))
    if not principals:
        return True
    for principal in principals:
        if principal.startswith("user:") and principal[5:] == username:
            return True
        if principal.startswith("role:") and principal[5:] in roles:
            return True
    return False


def user_can_write_collection(
    collection_record: Dict[str, Any], session: Dict[str, Any]
) -> bool:
    if user_has_stig_admin(session):
        return True
    if not user_can_read_collection(collection_record, session):
        return False
    caps = session.get("capabilities") or {}
    return bool(caps.get("stig_write"))


def filter_collections_for_user(
    records: Iterable[Dict[str, Any]], session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [r for r in records if user_can_read_collection(r, session)]
