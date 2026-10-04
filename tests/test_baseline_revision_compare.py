"""STIG library revision compare (read-only report)."""

from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

if "splunk" not in sys.modules:
    persistconn = types.ModuleType("splunk.persistconn")
    application = types.ModuleType("splunk.persistconn.application")

    class PersistentServerConnectionApplication:  # noqa: D101
        def __init__(self, *args, **kwargs):
            pass

    application.PersistentServerConnectionApplication = (
        PersistentServerConnectionApplication
    )
    splunk = types.ModuleType("splunk")
    splunk.persistconn = persistconn
    sys.modules["splunk"] = splunk
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application

from services import baseline_revision_compare as compare_svc  # noqa: E402
import json  # noqa: E402
import stig_rest_handler  # noqa: E402


class TestBaselineRevisionCompare(unittest.TestCase):
    def test_detects_added_removed_and_changed(self):
        service = MagicMock()
        from_bl = {"_key": "b1", "stig_id": "Example_STIG", "version": "V1R1"}
        to_bl = {"_key": "b2", "stig_id": "Example_STIG", "version": "V2R1"}
        from_rules = [
            {
                "_key": "r1",
                "group_id": "V-1",
                "rule_id": "SV-1",
                "rule_title": "Stay",
                "check_content": "same",
                "check_content_hash": "h1",
            },
            {
                "_key": "r2",
                "group_id": "V-2",
                "rule_id": "SV-2",
                "rule_title": "Gone",
                "check_content": "old",
                "check_content_hash": "h2",
            },
            {
                "_key": "r3",
                "group_id": "V-3",
                "rule_id": "SV-3",
                "rule_title": "Edit",
                "check_content": "before",
                "check_content_hash": "h3",
            },
        ]
        to_rules = [
            from_rules[0],
            {
                "_key": "r4",
                "group_id": "V-4",
                "rule_id": "SV-4",
                "rule_title": "New rule",
                "check_content": "new",
                "check_content_hash": "h4",
            },
            {
                "_key": "r5",
                "group_id": "V-3",
                "rule_id": "SV-3",
                "rule_title": "Edit",
                "check_content": "after",
                "check_content_hash": "h3b",
            },
        ]
        with patch.object(
            compare_svc.baselines_svc, "get_baseline", side_effect=lambda _s, bid: from_bl if bid == "b1" else to_bl
        ), patch.object(
            compare_svc.baselines_svc,
            "list_baseline_rules",
            side_effect=lambda _s, bid: from_rules if bid == "b1" else to_rules,
        ):
            report = compare_svc.compare_baselines(service, "b1", "b2")

        self.assertEqual(report["summary"]["unchanged"], 1)
        self.assertEqual(report["summary"]["added"], 1)
        self.assertEqual(report["summary"]["removed"], 1)
        self.assertEqual(report["summary"]["changed"], 1)
        self.assertEqual(report["added"][0]["rule_id"], "SV-4")
        self.assertEqual(report["removed"][0]["rule_id"], "SV-2")
        changed = report["changed"][0]
        self.assertTrue(changed["check_content_hash_changed"])
        self.assertFalse(changed["review_would_carry_forward"])
        self.assertIn("check_content", changed["fields"])

    def test_rejects_different_stig(self):
        service = MagicMock()
        with patch.object(
            compare_svc.baselines_svc,
            "get_baseline",
            side_effect=lambda _s, bid: {"_key": bid, "stig_id": bid},
        ):
            with self.assertRaises(ValueError):
                compare_svc.compare_baselines(service, "b1", "b2")

    def test_rejects_same_baseline(self):
        with self.assertRaises(ValueError):
            compare_svc.compare_baselines(MagicMock(), "b1", "b1")


class TestBaselineRevisionCompareRest(unittest.TestCase):
    def _dispatch(self, query):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": {
                "authtoken": "token",
                "user": "reader",
                "capabilities": {"stig_read": True},
            },
            "rest_path": "stig_baselines/compare",
            "query": query,
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(
        stig_rest_handler.baselines_svc,
        "visible_baseline_id_set",
        return_value={"b1", "b2"},
    )
    @patch.object(stig_rest_handler.baseline_revision_compare_svc, "compare_baselines")
    def test_get_compare(self, mock_compare, _visible):
        mock_compare.return_value = {"summary": {"changed": 0}}
        resp = self._dispatch(
            [["from_baseline_id", "b1"], ["to_baseline_id", "b2"]]
        )
        self.assertEqual(resp["status"], 200)
        mock_compare.assert_called_once()

    @patch.object(
        stig_rest_handler.baselines_svc,
        "visible_baseline_id_set",
        return_value={"b1"},
    )
    def test_compare_hidden_baseline_404(self, _visible):
        resp = self._dispatch(
            [["from_baseline_id", "b1"], ["to_baseline_id", "b2"]]
        )
        self.assertEqual(resp["status"], 404)


if __name__ == "__main__":
    unittest.main()
