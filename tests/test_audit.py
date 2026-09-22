"""Unit tests for structured audit logging and index emission."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import audit  # noqa: E402


class AuditEventShapeTests(unittest.TestCase):
    def test_build_event_workspace_from_collection_entity(self) -> None:
        event = audit.build_event(
            "create",
            "stig_collection",
            "col-1",
            "admin",
            {"name": "Lab"},
        )
        self.assertEqual(event["action"], "create")
        self.assertEqual(event["entity_type"], "stig_collection")
        self.assertEqual(event["entity_id"], "col-1")
        self.assertEqual(event["user"], "admin")
        self.assertEqual(event["workspace_id"], "col-1")
        self.assertEqual(event["object"], "stig_collection:col-1")
        self.assertIn("time", event)
        self.assertEqual(event["details"], {"name": "Lab"})

    def test_build_event_workspace_from_details(self) -> None:
        event = audit.build_event(
            "update",
            "stig_host",
            "host-9",
            "analyst",
            {"stig_collection_id": "ws-42", "hostname": "web-01"},
        )
        self.assertEqual(event["workspace_id"], "ws-42")
        self.assertEqual(event["object"], "stig_host:host-9")


class AuditLogEventTests(unittest.TestCase):
    @patch.object(audit, "emit_indexed")
    @patch.object(audit.logger, "info")
    def test_log_event_emits_logger_and_index(self, mock_info, mock_index) -> None:
        audit.log_event(
            "delete",
            "stig_checklist",
            "chk-1",
            "admin",
            {"stig_collection_id": "ws-1"},
        )
        mock_info.assert_called_once()
        self.assertEqual(mock_info.call_args[0][0], "stig_audit %s")
        payload = json.loads(mock_info.call_args[0][1])
        self.assertEqual(payload["action"], "delete")
        self.assertEqual(payload["entity_type"], "stig_checklist")
        mock_index.assert_called_once()
        indexed = mock_index.call_args[0][0]
        self.assertEqual(indexed["workspace_id"], "ws-1")
        self.assertEqual(indexed["user"], "admin")

    @patch("services.hec.emit_indexed_events")
    def test_emit_indexed_calls_hec_helper(self, mock_emit) -> None:
        event = audit.build_event("import", "stig_checklist", "x", "admin", {})
        audit.set_indexing_context("session-key-abc")
        try:
            audit.emit_indexed(event)
        finally:
            audit.clear_indexing_context()
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args[1]
        self.assertEqual(kwargs["index"], "stig_audit")
        self.assertEqual(kwargs["sourcetype"], "stig:audit")
        self.assertEqual(kwargs["session_key"], "session-key-abc")


if __name__ == "__main__":
    unittest.main()
