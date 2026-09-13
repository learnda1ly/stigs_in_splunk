"""Structured audit logging for PoC."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("stigs_in_splunk.audit")


def log_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    user: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user": user,
        "details": details or {},
    }
    logger.info("stig_audit %s", json.dumps(payload, sort_keys=True))
