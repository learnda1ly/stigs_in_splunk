"""Review history retention config and enforcement."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import review_history as history_svc  # noqa: E402
from services import review_history_config as config_svc  # noqa: E402


class ReviewHistoryConfigPolicyTests(unittest.TestCase):
    def test_defaults(self):
        policy = config_svc.default_policy()
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["max_records_per_review"], 15)

    def test_normalize_rejects_over_cap(self):
        with self.assertRaises(ValueError):
            config_svc.normalize_policy({"enabled": True, "max_records_per_review": 20})

    def test_disabled_ignores_max(self):
        policy = config_svc.normalize_policy({"enabled": False, "max_records_per_review": 99})
        self.assertFalse(policy["enabled"])


class ReviewHistoryRetentionTests(unittest.TestCase):
    def _review(self):
        return {
            "_key": "r1",
            "checklist_id": "cl1",
            "status": "open",
            "finding_details": "",
            "comments": "",
            "workflow_state": "draft",
            "ingest_lock": False,
        }

    def test_record_skipped_when_disabled(self):
        service = MagicMock()
        before = self._review()
        after = dict(before, status="not_a_finding")
        with patch.object(
            config_svc,
            "policy_for_collection_id",
            return_value={"enabled": False, "max_records_per_review": 15},
        ), patch.object(history_svc.kv_client, "insert_record") as mock_insert:
            result = history_svc.record_review_change(
                service, before, after, "alice", action="update"
            )
        self.assertIsNone(result)
        mock_insert.assert_not_called()

    def test_trim_after_insert(self):
        service = MagicMock()
        before = self._review()
        after = dict(before, status="not_a_finding")
        coll = MagicMock()
        existing = [
            {"_key": f"h{i}", "review_id": "r1", "created_at": i}
            for i in range(1, 16)
        ]
        with patch.object(
            config_svc,
            "policy_for_collection_id",
            return_value={"enabled": True, "max_records_per_review": 15},
        ), patch.object(history_svc, "_context_for_review", return_value={
            "stig_collection_id": "ws1",
            "checklist_id": "cl1",
            "host_id": "h1",
            "baseline_id": "b1",
            "group_id": "",
            "rule_id": "V-1",
            "rule_version": "1",
        }), patch.object(
            history_svc.kv_client, "get_collection", return_value=coll
        ), patch.object(
            history_svc.kv_client, "insert_record", return_value={"_key": "new"}
        ), patch.object(
            history_svc.kv_client, "query_all", return_value=existing + [{"_key": "new", "review_id": "r1", "created_at": 99}]
        ), patch.object(history_svc.kv_client, "delete_record") as mock_delete:
            history_svc.record_review_change(service, before, after, "alice")
        mock_delete.assert_called_once()
        self.assertEqual(mock_delete.call_args[0][1], "h1")

    def test_list_applies_cap_before_pagination(self):
        service = MagicMock()
        session = {"user": "alice", "capabilities": {"stig_read": True}}
        rows = [
            {"_key": f"h{i}", "review_id": "r1", "created_at": i, "summary": str(i)}
            for i in range(20)
        ]
        with patch.object(
            history_svc, "_require_visible_review", return_value={"_key": "r1", "checklist_id": "cl1"}
        ), patch.object(
            history_svc.checklists_svc,
            "get_checklist",
            return_value={"stig_collection_id": "ws1"},
        ), patch.object(
            config_svc,
            "policy_for_collection_id",
            return_value={"enabled": True, "max_records_per_review": 15},
        ), patch.object(history_svc.kv_client, "get_collection"), patch.object(
            history_svc.kv_client, "query_all", return_value=rows
        ):
            out = history_svc.list_review_history(
                service, "r1", session, {"limit": 100, "offset": 0}
            )
        self.assertEqual(out["pagination"]["total"], 15)
        self.assertEqual(out["pagination"]["limit"], 100)
        self.assertEqual(len(out["history"]), 15)
        self.assertEqual(out["history"][0]["created_at"], 19)

    def test_list_empty_when_disabled(self):
        service = MagicMock()
        session = {"user": "alice", "capabilities": {"stig_read": True}}
        rows = [{"_key": "h1", "review_id": "r1", "created_at": 1}]
        with patch.object(
            history_svc, "_require_visible_review", return_value={"_key": "r1", "checklist_id": "cl1"}
        ), patch.object(
            history_svc.checklists_svc,
            "get_checklist",
            return_value={"stig_collection_id": "ws1"},
        ), patch.object(
            config_svc,
            "policy_for_collection_id",
            return_value={"enabled": False, "max_records_per_review": 15},
        ), patch.object(history_svc.kv_client, "get_collection"), patch.object(
            history_svc.kv_client, "query_all", return_value=rows
        ):
            out = history_svc.list_review_history(service, "r1", session)
        self.assertEqual(out["history"], [])
        self.assertEqual(out["pagination"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
