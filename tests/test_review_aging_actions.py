"""Review aging action rules and apply (dry-run / execute)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import review_aging as aging_svc  # noqa: E402
from services import review_aging_actions as actions_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _ActionKv:
    def __init__(self) -> None:
        self.now = 2_000_000_000.0
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {
                "ws1": {
                    "_key": "ws1",
                    "name": "Workspace",
                    "review_aging_config": "",
                }
            },
            "stig_editor_settings": {},
            "stig_checklists": {
                "cl1": {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                }
            },
            "stig_hosts": {
                "h1": {
                    "_key": "h1",
                    "stig_collection_id": "ws1",
                    "hostname": "host1",
                    "label_ids": "[]",
                },
            },
            "stig_reviews": {
                "r1": {
                    "_key": "r1",
                    "checklist_id": "cl1",
                    "baseline_id": "b1",
                    "group_id": "V-1",
                    "rule_id": "SV-1",
                    "status": "open",
                    "workflow_state": "accepted",
                    "updated_at": self.now - (120 * 86400),
                    "submitted_at": self.now - (120 * 86400),
                }
            },
            "stig_review_history": {},
            "stig_baselines": {},
            "stig_baseline_rules": {},
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

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]):
        key = record.get("_key") or "settings1"
        record = dict(record)
        record["_key"] = key
        coll._rows[key] = record
        return record

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)


class ReviewAgingRulesTests(unittest.TestCase):
    def test_normalize_rule_assigns_id_and_interval(self):
        rule = aging_svc.normalize_rule(
            {
                "enabled": True,
                "action": "delete",
                "interval_days": 30,
                "trigger_field": "ts",
            }
        )
        self.assertTrue(rule["id"])
        self.assertEqual(rule["action"], "delete")
        self.assertEqual(aging_svc.rule_interval_seconds(rule), 30 * 86400)

    def test_invalid_action_rejected(self):
        with self.assertRaises(ValueError):
            aging_svc.normalize_rule({"action": "explode"})


class ReviewAgingApplyTests(unittest.TestCase):
    def setUp(self):
        self.kv = _ActionKv()
        rules = [
            {
                "id": "rule1",
                "ordinal": 0,
                "enabled": True,
                "trigger_field": "touch_ts",
                "interval_days": 90,
                "action": "set_status_saved",
                "target": {"type": "collection"},
                "statuses": ["open"],
                "workflow_states": ["accepted"],
            }
        ]
        self.kv.tables["stig_collections"]["ws1"]["review_aging_config"] = json.dumps(
            {"rules": rules}
        )

    @contextmanager
    def _patch_kv(self):
        kwargs = {
            "get_collection": self.kv.get_collection,
            "query_all": self.kv.query_all,
            "get_by_key": self.kv.get_by_key,
            "update_record": self.kv.update_record,
            "insert_record": self.kv.insert_record,
            "delete_record": self.kv.delete_record,
        }
        with patch.multiple(aging_svc.kv_client, **kwargs), patch.multiple(
            actions_svc.kv_client, **kwargs
        ):
            yield

    @patch.object(actions_svc.collections_svc, "get_collection")
    @patch("services.grants.workspace_context")
    @patch.object(actions_svc.reporting_svc, "_collection_workspace_context")
    @patch.object(actions_svc.baselines_svc, "get_baseline", return_value={})
    @patch.object(actions_svc.reporting_svc, "_rule_meta_index", return_value={})
    def test_dry_run_does_not_mutate(
        self, _meta, _baseline, mock_ctx, mock_workspace, mock_get_collection
    ):
        mock_get_collection.side_effect = (
            lambda _s, cid: dict(self.kv.tables["stig_collections"].get(cid) or {})
        )
        aging_json = self.kv.tables["stig_collections"]["ws1"]["review_aging_config"]
        mock_workspace.return_value = (
            {"_key": "ws1", "review_aging_config": aging_json},
            MagicMock(can_write=True),
            [],
        )
        mock_ctx.return_value = {
            "checklist_by_id": {"cl1": self.kv.tables["stig_checklists"]["cl1"]},
            "host_by_id": {"h1": self.kv.tables["stig_hosts"]["h1"]},
            "baselines": {},
            "severity_index": {},
        }
        with self._patch_kv():
            with patch.object(aging_svc, "now_epoch", return_value=self.kv.now):
                out = actions_svc.apply_collection_rules(
                    MagicMock(),
                    "ws1",
                    "owner",
                    {"user": "owner"},
                    execute=False,
                )
        self.assertTrue(out["dry_run"])
        self.assertGreater(out["matched_count"], 0)
        self.assertEqual(out["acted_count"], 0)
        self.assertEqual(
            self.kv.tables["stig_reviews"]["r1"]["workflow_state"], "accepted"
        )

    @patch.object(actions_svc.collections_svc, "get_collection")
    @patch("services.grants.workspace_context")
    @patch.object(actions_svc.reporting_svc, "_collection_workspace_context")
    @patch.object(actions_svc.baselines_svc, "get_baseline", return_value={})
    @patch.object(actions_svc.reporting_svc, "_rule_meta_index", return_value={})
    @patch.object(actions_svc.review_history_svc, "record_review_change")
    @patch.object(actions_svc.audit, "log_event")
    def test_execute_updates_review(
        self,
        _audit,
        _history,
        _meta,
        _baseline,
        mock_ctx,
        mock_workspace,
        mock_get_collection,
    ):
        mock_get_collection.side_effect = (
            lambda _s, cid: dict(self.kv.tables["stig_collections"].get(cid) or {})
        )
        aging_json = self.kv.tables["stig_collections"]["ws1"]["review_aging_config"]
        mock_workspace.return_value = (
            {"_key": "ws1", "review_aging_config": aging_json},
            MagicMock(can_write=True),
            [],
        )
        mock_ctx.return_value = {
            "checklist_by_id": {"cl1": self.kv.tables["stig_checklists"]["cl1"]},
            "host_by_id": {"h1": self.kv.tables["stig_hosts"]["h1"]},
            "baselines": {},
            "severity_index": {},
        }
        with self._patch_kv():
            with patch.object(aging_svc, "now_epoch", return_value=self.kv.now):
                out = actions_svc.apply_collection_rules(
                    MagicMock(),
                    "ws1",
                    "owner",
                    {"user": "owner"},
                    execute=True,
                )
        self.assertFalse(out["dry_run"])
        self.assertGreater(out["acted_count"], 0)
        self.assertEqual(
            self.kv.tables["stig_reviews"]["r1"]["workflow_state"], "draft"
        )

    def test_job_disabled_blocks_global_apply(self):
        with self._patch_kv():
            out = actions_svc.apply_all_workspaces(
                MagicMock(), "admin", {"user": "admin"}, execute=True
            )
        self.assertFalse(out["job_enabled"])

    def test_set_result_informational_action(self):
        review = {
            "_key": "r1",
            "status": "open",
            "workflow_state": "accepted",
        }
        with self._patch_kv():
            stored = actions_svc._apply_update_action(
                MagicMock(),
                review,
                actions_svc.ACTION_SET_RESULT_INFORMATIONAL,
                "admin",
            )
        self.assertEqual(stored["status"], "informational")
        self.assertEqual(stored["workflow_state"], "draft")
        self.assertTrue(
            actions_svc.review_already_at_action_target(
                stored, actions_svc.ACTION_SET_RESULT_INFORMATIONAL
            )
        )
        self.assertFalse(
            actions_svc.review_already_at_action_target(
                stored, actions_svc.ACTION_SET_RESULT_NOT_CHECKED
            )
        )


if __name__ == "__main__":
    unittest.main()
