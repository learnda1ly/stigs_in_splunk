"""Helpers for UCC AdminExternalHandler classes that persist to KV."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

import kv_client


def normalize_roles(raw: Any) -> List[str]:
    """MConfigHandler may expose userRoles as a string, not a list."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [part for part in raw.replace(",", " ").split() if part]
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw).strip()]


def _capabilities_map(raw: Any) -> Dict[str, bool]:
    if isinstance(raw, dict):
        return {str(key): bool(val) for key, val in raw.items()}
    if isinstance(raw, (list, tuple, set)):
        return {str(item): True for item in raw if str(item).strip()}
    return {}


def _context_session(session_key: str) -> Dict[str, Any]:
    data = kv_client._simple_request(
        session_key, "GET", "/services/authentication/current-context"
    )
    if not isinstance(data, dict):
        return {}
    entries = data.get("entry") or []
    content = {}
    if entries and isinstance(entries[0], dict):
        content = entries[0].get("content") or {}
    elif "username" in data or "roles" in data:
        content = data
    if not isinstance(content, dict):
        return {}
    return {
        "user": content.get("username") or content.get("realname") or "",
        "roles": normalize_roles(content.get("roles")),
        "capabilities": _capabilities_map(content.get("capabilities")),
    }


def handler_username(handler) -> str:
    name = getattr(handler, "userName", None)
    if isinstance(name, str) and name.strip() and name not in ("-", "unknown"):
        return name.strip()
    return "unknown"


def handler_session(handler) -> Dict[str, Any]:
    session_key = handler.getSessionKey()
    session: Dict[str, Any] = {
        "authtoken": session_key,
        "user": handler_username(handler),
        "roles": normalize_roles(getattr(handler, "userRoles", None)),
        "capabilities": {},
    }
    try:
        extra = _context_session(session_key)
    except Exception:
        extra = {}
    if extra.get("user"):
        session["user"] = extra["user"]
    if extra.get("roles"):
        merged = list(session["roles"])
        for role in extra["roles"]:
            if role not in merged:
                merged.append(role)
        session["roles"] = merged
    if extra.get("capabilities"):
        session["capabilities"] = extra["capabilities"]
    return session


def connect(handler):
    return kv_client.connect(handler.getSessionKey())


def _stringify(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "1" if val else "0"
    return str(val)


def fill(conf_info, name: str, fields: Dict[str, Any]) -> None:
    item = conf_info[name]
    for key, val in fields.items():
        item[key] = _stringify(val)


def as_conf_entities(handler, rows: Iterable[Tuple[str, Dict[str, Any]]]):
    """Build UCC RestEntity rows (includes eai:acl/app so the table renders)."""
    from splunktaucclib.rest_handler.entity import RestEntity

    app = getattr(handler, "appName", None) or "stigs_in_splunk"
    user = handler_username(handler)
    if user == "unknown":
        user = "nobody"
    model = handler.endpoint.model(None)
    entities = []
    for name, fields in rows:
        content = {key: _stringify(val) for key, val in fields.items()}
        content.setdefault("disabled", "0")
        entities.append(RestEntity(name, content, model, user, app))
    return entities


def decode_uploaded_file(raw: Any) -> bytes:
    if raw is None:
        return b""
    if isinstance(raw, bytes):
        if raw[:2] == b"PK":
            return raw
        stripped_bytes = raw.strip()
        if stripped_bytes[:1] in (b"<", b"{", b"["):
            return stripped_bytes
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
    stripped = text.strip()
    if not stripped:
        return b""
    if stripped.startswith("<") or stripped.startswith("{") or stripped.startswith("["):
        return stripped.encode("utf-8")
    if stripped.startswith("PK"):
        try:
            return stripped.encode("latin-1")
        except UnicodeEncodeError:
            return stripped.encode("utf-8", errors="replace")
    try:
        return base64.b64decode(stripped, validate=False)
    except (ValueError, TypeError):
        return stripped.encode("utf-8")


def principals_to_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return json.dumps(parsed, separators=(",", ":"))
    except (TypeError, ValueError):
        pass
    return text


def parse_principals(value: Any) -> Optional[List[str]]:
    text = principals_to_text(value)
    if not text:
        return None
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("access_principals must be a JSON array")
    return [str(item) for item in parsed]
