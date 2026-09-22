"""Tests for per-workspace review aging policy and stale review queries."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import review_aging as aging_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _AgingKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {
                "ws1": {
                    "_key": "ws1",
                    "name": "Workspace",
                    "review_aging_config": "",
                }
            },
            "stig_checklists": {
                "cl1": {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                }
            },
            "stig_hosts": {
                "h1": {"_key": "h1", "stig_collection_id": "ws1", "hostname": "host1"},
            },
            "stig_reviews": {},
            "stig_baseline_rules": {},
            "stig_baselines": {},
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables[name])

    def query_all(
        self, coll: _MemColl, query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query = query or {}
        out: List[Dict[str, Any]] = []
        for rec in coll._rows.values():
            if all(rec.get(k) == v for k, v in query.items()):
                out.append(dict(rec))
        return out

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]):
        coll._rows[key] = dict(record)
        return dict(record)


class ReviewAgingPolicyTests(unittest.TestCase):
    def test_default_config_disabled(self):
        cfg = aging_svc.default_config()
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["stale_after_days"], 90)

    def test_normalize_rejects_invalid_status(self):
        with self.assertRaises(ValueError):
            aging_svc.normalize_config({"statuses": ["bogus"]})

    def test_hours_override_days(self):
        cfg = aging_svc.normalize_config(
            {"stale_after_days": 30, "stale_after_hours": 12}
        )
        self.assertEqual(aging_svc.stale_threshold_seconds(cfg), 12 * 3600)


class ReviewAgingStaleTests(unittest.TestCase):
    def setUp(self):
        self.kv = _AgingKv()
        self.now = 1_700_000_000.0
        self.kv.tables["stig_reviews"]["r1"] = {
            "_key": "r1",
            "checklist_id": "cl1",
            "baseline_id": "b1",
            "group_id": "V-1",
            "rule_id": "SV-1",
            "status": "open",
            "workflow_state": "accepted",
            "updated_at": self.now - (100 * 86400),
        }

    def _patch_kv(self):
        return patch.multiple(
            aging_svc.kv_client,
            get_collection=self.kv.get_collection,
            query_all=self.kv.query_all,
            get_by_key=self.kv.get_by_key,
            update_record=self.kv.update_record,
        )

    @patch("services.grants.workspace_context")
    @patch.object(aging_svc.reporting_svc, "_rule_meta_index", return_value={})
    @patch.object(aging_svc.baselines_svc, "list_baselines", return_value=[])
    @patch.object(aging_svc.reporting_svc, "_collection_workspace_context")
    def test_stale_when_enabled(
        self, mock_ctx, _baselines, _meta, mock_workspace
    ):
        aging_json = '{"enabled": true, "stale_after_days": 90}'
        self.kv.tables["stig_collections"]["ws1"]["review_aging_config"] = aging_json
        mock_workspace.return_value = (
            {"_key": "ws1", "review_aging_config": aging_json},
            MagicMock(can_read=True),
            [],
        )
        mock_ctx.return_value = {
            "checklist_by_id": {"cl1": self.kv.tables["stig_checklists"]["cl1"]},
            "host_by_id": {"h1": self.kv.tables["stig_hosts"]["h1"]},
            "baselines": {},
            "severity_index": {},
        }
        with self._patch_kv():
            with patch.object(aging_svc, "now_epoch", return_value=self.now):
                body = aging_svc.list_stale_reviews(
                    MagicMock(), "ws1", {"user": "u"}, {}
                )
        self.assertTrue(body["enabled"])
        self.assertEqual(body["stale_count"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertTrue(body["items"][0].get("aging_stale"))

    @patch("services.grants.workspace_context")
    @patch.object(aging_svc.reporting_svc, "_collection_workspace_context")
    def test_disabled_returns_empty(self, mock_ctx, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True),
            [],
        )
        mock_ctx.return_value = {
            "checklist_by_id": {},
            "host_by_id": {},
            "baselines": {},
            "severity_index": {},
        }
        with self._patch_kv():
            body = aging_svc.list_stale_reviews(
                MagicMock(), "ws1", {"user": "u"}, {}
            )
        self.assertFalse(body["enabled"])
        self.assertEqual(body["stale_count"], 0)
        self.assertEqual(body["items"], [])

    @patch("services.grants.workspace_context")
    def test_acl_denied_read(self, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=False),
            [],
        )
        with self._patch_kv():
            with self.assertRaises(KeyError):
                aging_svc.list_stale_reviews(MagicMock(), "ws1", {"user": "u"}, {})

    @patch("services.grants.workspace_context")
    @patch.object(aging_svc, "collections_svc")
    def test_patch_requires_write(self, mock_collections, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_write=False),
            [],
        )
        with self.assertRaises(PermissionError):
            aging_svc.patch_config(
                MagicMock(),
                "ws1",
                {"review_aging": {"enabled": True}},
                "u",
                {"user": "u"},
            )

    @patch("services.grants.workspace_context")
    @patch.object(aging_svc, "collections_svc")
    def test_patch_validation(self, mock_collections, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = self.kv.tables["stig_collections"]["ws1"]
        with self._patch_kv():
            with self.assertRaises(ValueError):
                aging_svc.patch_config(
                    MagicMock(),
                    "ws1",
                    {"review_aging": {"stale_after_days": 0}},
                    "u",
                    {"user": "u"},
                )

    @patch("services.grants.workspace_context")
    @patch.object(aging_svc, "collections_svc")
    def test_patch_persists_config(self, mock_collections, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = self.kv.tables["stig_collections"]["ws1"]
        with self._patch_kv():
            out = aging_svc.patch_config(
                MagicMock(),
                "ws1",
                {"review_aging": {"enabled": True, "stale_after_days": 45}},
                "u",
                {"user": "u"},
            )
        self.assertTrue(out["review_aging"]["enabled"])
        stored = self.kv.tables["stig_collections"]["ws1"]["review_aging_config"]
        self.assertIn("45", stored)


if __name__ == "__main__":
    unittest.main()
