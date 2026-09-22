"""Cross-revision review merge (check_content_hash) service tests."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import revision_upgrade as upgrade_svc  # noqa: E402


class _MemColl:
    def __init__(self, name: str, rows: Dict[str, Dict[str, Any]]):
        self.name = name
        self._rows = rows


class _MemKv:
    def __init__(self):
        self.checklists: Dict[str, Dict[str, Any]] = {}
        self.reviews: Dict[str, Dict[str, Any]] = {}
        self._seq = 0

    def _coll(self, name: str) -> _MemColl:
        if name == "stig_checklists":
            return _MemColl(name, self.checklists)
        if name == "stig_reviews":
            return _MemColl(name, self.reviews)
        raise KeyError(name)

    def get_collection(self, _service, name: str) -> _MemColl:
        return self._coll(name)

    def query_all(self, coll: _MemColl, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        query = query or {}
        out = []
        for rec in coll._rows.values():
            ok = True
            for key, val in query.items():
                if rec.get(key) != val:
                    ok = False
                    break
            if ok:
                out.append(dict(rec))
        return out

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        self._seq += 1
        key = record.get("_key") or f"rev{self._seq}"
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)

    @staticmethod
    def kv_record(rec: Dict[str, Any]) -> Dict[str, Any]:
        return rec


class TestRevisionUpgrade(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.session = {"user": "writer", "capabilities": {"stig_write": True}}
        self.kv = _MemKv()
        self.kv.checklists["cl1"] = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
            "host_id": "h1",
            "baseline_id": "base_v1",
            "title": "Test",
        }
        self.baselines = {
            "base_v1": {"_key": "base_v1", "stig_id": "Example_STIG", "version": "V1R1"},
            "base_v2": {"_key": "base_v2", "stig_id": "Example_STIG", "version": "V1R2"},
        }
        self.rules_v1 = [
            {
                "group_id": "V-1",
                "rule_id": "SV-1",
                "rule_version": "1.2",
                "check_content_hash": "hash_a",
            },
            {
                "group_id": "V-2",
                "rule_id": "SV-2",
                "rule_version": "1.0",
                "check_content_hash": "hash_b",
            },
        ]
        self.rules_v2 = [
            {
                "group_id": "V-1",
                "rule_id": "SV-1",
                "rule_version": "1.3",
                "check_content_hash": "hash_a",
            },
            {
                "group_id": "V-2",
                "rule_id": "SV-2",
                "rule_version": "1.1",
                "check_content_hash": "hash_b_changed",
            },
            {
                "group_id": "V-3",
                "rule_id": "SV-3",
                "rule_version": "1.0",
                "check_content_hash": "hash_c",
            },
        ]

    def _seed_reviews(self, rows: List[Dict[str, Any]]) -> None:
        for idx, row in enumerate(rows, start=1):
            self.kv.reviews[f"r{idx}"] = {
                "_key": f"r{idx}",
                "checklist_id": "cl1",
                "baseline_id": "base_v1",
                **row,
            }

    @patch("services.revision_upgrade.audit.log_event")
    @patch("services.revision_upgrade.checklists_svc.get_checklist")
    @patch("services.revision_upgrade.baselines_svc.list_baseline_rules")
    @patch("services.revision_upgrade.baselines_svc.get_baseline")
    @patch("services.revision_upgrade.kv_client")
    def test_hash_match_merges_assessor_state(
        self, mock_kv, mock_get_bl, mock_list_rules, mock_get_cl, _audit
    ):
        mock_kv.get_collection.side_effect = self.kv.get_collection
        mock_kv.query_all.side_effect = self.kv.query_all
        mock_kv.update_record.side_effect = self.kv.update_record
        mock_kv.insert_record.side_effect = self.kv.insert_record
        mock_kv.delete_record.side_effect = self.kv.delete_record
        mock_kv.kv_record.side_effect = self.kv.kv_record

        mock_get_cl.return_value = dict(self.kv.checklists["cl1"])
        mock_get_bl.side_effect = lambda _s, key: dict(self.baselines[key])
        mock_list_rules.side_effect = lambda _s, bid: (
            list(self.rules_v2) if bid == "base_v2" else list(self.rules_v1)
        )

        self._seed_reviews(
            [
                {
                    "group_id": "V-1",
                    "rule_id": "SV-1",
                    "rule_version": "1.2",
                    "check_content_hash": "hash_a",
                    "status": "not_a_finding",
                    "finding_details": "ok",
                    "comments": "c1",
                    "workflow_state": "draft",
                    "ingest_lock": False,
                },
                {
                    "group_id": "V-2",
                    "rule_id": "SV-2",
                    "rule_version": "1.0",
                    "check_content_hash": "hash_b",
                    "status": "open",
                    "finding_details": "bad",
                    "comments": "",
                    "workflow_state": "draft",
                    "ingest_lock": False,
                },
            ]
        )

        result = upgrade_svc.upgrade_checklist(
            self.service, "cl1", "base_v2", "writer", self.session
        )
        self.assertEqual(result["merged"], 1)
        self.assertEqual(result["reset"], 1)
        self.assertEqual(result["added"], 1)
        self.assertEqual(self.kv.checklists["cl1"]["baseline_id"], "base_v2")

        merged = self.kv.reviews["r1"]
        self.assertEqual(merged["status"], "not_a_finding")
        self.assertEqual(merged["finding_details"], "ok")
        self.assertEqual(merged["rule_version"], "1.3")
        self.assertEqual(merged["check_content_hash"], "hash_a")

        reset = self.kv.reviews["r2"]
        self.assertEqual(reset["status"], "not_reviewed")
        self.assertEqual(reset["finding_details"], "")
        self.assertEqual(reset["check_content_hash"], "hash_b_changed")

    @patch("services.revision_upgrade.audit.log_event")
    @patch("services.revision_upgrade.checklists_svc.get_checklist")
    @patch("services.revision_upgrade.baselines_svc.list_baseline_rules")
    @patch("services.revision_upgrade.baselines_svc.get_baseline")
    @patch("services.revision_upgrade.kv_client")
    def test_governed_rows_preserved_on_hash_mismatch(
        self, mock_kv, mock_get_bl, mock_list_rules, mock_get_cl, _audit
    ):
        mock_kv.get_collection.side_effect = self.kv.get_collection
        mock_kv.query_all.side_effect = self.kv.query_all
        mock_kv.update_record.side_effect = self.kv.update_record
        mock_kv.insert_record.side_effect = self.kv.insert_record
        mock_kv.delete_record.side_effect = self.kv.delete_record
        mock_kv.kv_record.side_effect = self.kv.kv_record

        mock_get_cl.return_value = dict(self.kv.checklists["cl1"])
        mock_get_bl.side_effect = lambda _s, key: dict(self.baselines[key])
        mock_list_rules.return_value = list(self.rules_v2)

        self._seed_reviews(
            [
                {
                    "group_id": "V-2",
                    "rule_id": "SV-2",
                    "rule_version": "1.0",
                    "check_content_hash": "hash_b",
                    "status": "open",
                    "finding_details": "locked finding",
                    "workflow_state": "draft",
                    "ingest_lock": True,
                },
                {
                    "group_id": "V-1",
                    "rule_id": "SV-1",
                    "rule_version": "1.2",
                    "check_content_hash": "hash_a",
                    "status": "not_a_finding",
                    "finding_details": "accepted work",
                    "workflow_state": "accepted",
                    "ingest_lock": False,
                },
            ]
        )

        result = upgrade_svc.upgrade_checklist(
            self.service, "cl1", "base_v2", "writer", self.session
        )
        self.assertEqual(result["preserved"], 1)
        self.assertEqual(result["merged"], 1)

        locked = self.kv.reviews["r1"]
        self.assertEqual(locked["status"], "open")
        self.assertEqual(locked["finding_details"], "locked finding")
        self.assertEqual(locked["check_content_hash"], "hash_b_changed")

        accepted = self.kv.reviews["r2"]
        self.assertEqual(accepted["workflow_state"], "accepted")
        self.assertEqual(accepted["finding_details"], "accepted work")

    @patch("services.revision_upgrade.audit.log_event")
    @patch("services.revision_upgrade.upgrade_checklist")
    @patch("services.revision_upgrade.checklists_svc.list_checklists")
    @patch("services.revision_upgrade.baselines_svc.get_baseline")
    def test_collection_bulk_upgrade_filters_workspace(
        self, mock_get_bl, mock_list_cls, mock_upgrade, _audit
    ):
        mock_get_bl.return_value = self.baselines["base_v2"]
        mock_list_cls.return_value = [
            {"_key": "cl1", "baseline_id": "base_v1", "stig_collection_id": "ws1"},
            {"_key": "cl2", "baseline_id": "base_v1", "stig_collection_id": "ws1"},
            {"_key": "cl3", "baseline_id": "other", "stig_collection_id": "ws1"},
        ]
        mock_upgrade.side_effect = [
            {"checklist": {"_key": "cl1"}, "merged": 1},
            {"checklist": {"_key": "cl2"}, "merged": 2},
        ]

        def _get_bl(_s, key):
            if key == "base_v1":
                return self.baselines["base_v1"]
            if key == "other":
                return {"_key": "other", "stig_id": "Other_STIG"}
            return self.baselines.get(key)

        mock_get_bl.side_effect = _get_bl

        out = upgrade_svc.upgrade_collection_checklists(
            self.service,
            "ws1",
            "base_v2",
            "writer",
            self.session,
            from_baseline_id="base_v1",
        )
        self.assertEqual(out["upgraded"], 2)
        self.assertEqual(mock_upgrade.call_count, 2)


if __name__ == "__main__":
    unittest.main()
