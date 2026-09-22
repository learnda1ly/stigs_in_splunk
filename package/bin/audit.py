"""Structured audit logging and optional Splunk index emission."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from models import (
    APP_NAME,
    AUDIT_HEC_INPUT_NAME,
    AUDIT_HEC_STANZA,
    DEFAULT_AUDIT_INDEX,
    DEFAULT_AUDIT_SOURCETYPE,
)

logger = logging.getLogger("stigs_in_splunk.audit")

_ctx = threading.local()


def set_indexing_context(session_key: str = "") -> None:
    """Attach REST session key for receivers/simple fallback indexing."""
    _ctx.session_key = session_key or ""


def clear_indexing_context() -> None:
    _ctx.session_key = ""


def _indexing_session_key() -> str:
    return getattr(_ctx, "session_key", "") or ""


def _workspace_id(
    entity_type: str, entity_id: Optional[str], details: Dict[str, Any]
) -> str:
    for key in (
        "stig_collection_id",
        "workspace_id",
        "source_stig_collection_id",
        "destination_stig_collection_id",
    ):
        val = details.get(key)
        if val:
            return str(val)
    if entity_type == "stig_collection" and entity_id:
        return str(entity_id)
    return ""


def build_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    user: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Canonical audit event shape for logs and index emission."""
    details = details or {}
    eid = entity_id or ""
    return {
        "action": action,
        "entity_type": entity_type,
        "entity_id": eid,
        "object": f"{entity_type}:{eid}" if entity_type else eid,
        "user": user,
        "workspace_id": _workspace_id(entity_type, entity_id, details),
        "details": details,
        "time": time.time(),
        "source": APP_NAME,
    }


def log_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    user: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    event = build_event(action, entity_type, entity_id, user, details)
    log_payload = {
        "action": event["action"],
        "entity_type": event["entity_type"],
        "entity_id": event["entity_id"],
        "user": event["user"],
        "details": event["details"],
    }
    logger.info("stig_audit %s", json.dumps(log_payload, sort_keys=True))
    emit_indexed(event)


def emit_indexed(event: Dict[str, Any]) -> None:
    """Best-effort write to the audit index; always safe to call from mutations."""
    try:
        from services import hec as hec_svc

        hec_svc.emit_indexed_events(
            [event],
            index=DEFAULT_AUDIT_INDEX,
            sourcetype=DEFAULT_AUDIT_SOURCETYPE,
            session_key=_indexing_session_key(),
            hec_input_name=AUDIT_HEC_INPUT_NAME,
            hec_stanza=AUDIT_HEC_STANZA,
            source=APP_NAME,
        )
    except Exception as exc:
        logger.debug("audit_index_failed %s", exc)
