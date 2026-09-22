"""Assign baseline to host (idempotent checklist create)."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import access  # noqa: E402
from services import checklists as checklists_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _MemKv:
    def __init__(self):
        self.checklists: Dict[str, Dict[str, Any]] = {}
        self.reviews: Dict[str, Dict[str, Any]] = {}
        self._seq = 0

    def get_collection(self, _service, name: str) -> _MemColl:
        if name == "stig_checklists":
            return _MemColl(self.checklists)
        if name == "stig_reviews":
            return _MemColl(self.reviews)
        raise KeyError(name)

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

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        self._seq += 1
        key = record.get("_key") or f"cl{self._seq}"
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def batch_insert(self, coll: _MemColl, records: List[Dict[str, Any]]) -> None:
        for rec in records:
            self.insert_record(coll, rec)


def _session_write(user: str = "writer") -> Dict[str, Any]:
    return {
        "user": user,
        "roles": [],
        "capabilities": {"stig_read": True, "stig_write": True},
    }


class TestAssignStigToHost(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.session = _session_write()
        self.kv = _MemKv()
        self.host = {
            "_key": "host1",
            "stig_collection_id": "ws1",
            "hostname": "web01.example.com",
        }
        self.baseline = {
            "_key": "base1",
            "stig_id": "Example_STIG",
            "title": "Example STIG V1R1",
        }
        self.rules = [
            {
                "group_id": "V-1",
                "rule_id": "SV-1",
                "rule_version": "1.1",
                "check_content_hash": "abc",
            }
        ]

    @patch("services.checklists.audit.log_event")
    @patch("services.checklists.validation.persistable_valid", return_value=False)
    @patch("services.checklists.baselines_svc.list_baseline_rules")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.require_workspace_write")
    @patch("services.checklists.kv_client.batch_insert")
    @patch("services.checklists.kv_client.insert_record")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    def test_assign_creates_checklist_and_reviews(
        self,
        mock_get_coll,
        mock_query_all,
        mock_insert,
        mock_batch,
        mock_require_write,
        mock_get_host,
        mock_get_baseline,
        mock_list_rules,
        _mock_valid,
        _mock_audit,
    ):
        mock_get_host.return_value = self.host
        mock_get_baseline.return_value = self.baseline
        mock_list_rules.return_value = self.rules
        mock_get_coll.side_effect = self.kv.get_collection
        mock_query_all.side_effect = self.kv.query_all

        def _insert(coll, record):
            return self.kv.insert_record(coll, record)

        mock_insert.side_effect = _insert
        mock_batch.side_effect = self.kv.batch_insert

        checklist, created = checklists_svc.assign_stig_to_host(
            self.service,
            "host1",
            {"baseline_id": "base1"},
            "writer",
            self.session,
        )
        self.assertTrue(created)
        self.assertEqual(checklist["host_id"], "host1")
        self.assertEqual(checklist["baseline_id"], "base1")
        self.assertEqual(len(self.kv.reviews), 1)
        mock_require_write.assert_called()

    @patch("services.checklists.audit.log_event")
    @patch("services.checklists.grants_svc.workspace_context")
    @patch("services.checklists.grants_svc.require_workspace_write")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    def test_assign_idempotent_returns_existing(
        self,
        mock_get_coll,
        mock_query_all,
        mock_get_host,
        mock_require_write,
        mock_workspace_context,
        _mock_audit,
    ):
        self.kv.checklists["cl_existing"] = {
            "_key": "cl_existing",
            "stig_collection_id": "ws1",
            "host_id": "host1",
            "baseline_id": "base1",
            "title": "Existing",
        }
        mock_get_host.return_value = self.host
        mock_get_coll.side_effect = self.kv.get_collection
        mock_query_all.side_effect = self.kv.query_all
        coll = {"_key": "ws1"}
        ctx = access.resolve_workspace_access(coll, self.session)
        mock_workspace_context.return_value = (coll, ctx, [])

        checklist, created = checklists_svc.assign_stig_to_host(
            self.service,
            "host1",
            {"baseline_id": "base1"},
            "writer",
            self.session,
        )
        self.assertFalse(created)
        self.assertEqual(checklist["_key"], "cl_existing")

    @patch("services.checklists.grants_svc.require_workspace_write")
    @patch("services.checklists.hosts_svc.get_host")
    def test_assign_acl_denied_on_write(
        self, mock_get_host, mock_require_write
    ):
        mock_get_host.return_value = self.host
        mock_require_write.side_effect = PermissionError("write denied")

        with self.assertRaises(PermissionError):
            checklists_svc.assign_stig_to_host(
                self.service,
                "host1",
                {"baseline_id": "base1"},
                "reader",
                {"user": "reader", "capabilities": {"stig_read": True}},
            )

    @patch("services.checklists.audit.log_event")
    @patch("services.checklists.validation.persistable_valid", return_value=False)
    @patch("services.checklists.baseline_defaults_svc.resolve_baseline_id", return_value="default_base")
    @patch("services.checklists.baselines_svc.list_baseline_rules")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.require_workspace_write")
    @patch("services.checklists.kv_client.batch_insert")
    @patch("services.checklists.kv_client.insert_record")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    def test_assign_resolves_stig_id_via_workspace_default(
        self,
        mock_get_coll,
        mock_query_all,
        mock_insert,
        mock_batch,
        mock_require_write,
        mock_get_host,
        mock_get_baseline,
        mock_list_rules,
        mock_resolve,
        _mock_valid,
        _mock_audit,
    ):
        mock_get_host.return_value = self.host
        mock_get_baseline.return_value = {**self.baseline, "_key": "default_base"}
        mock_list_rules.return_value = self.rules
        mock_get_coll.side_effect = self.kv.get_collection
        mock_query_all.side_effect = self.kv.query_all
        mock_insert.side_effect = self.kv.insert_record
        mock_batch.side_effect = self.kv.batch_insert

        checklist, created = checklists_svc.assign_stig_to_host(
            self.service,
            "host1",
            {"stig_id": "Example_STIG"},
            "writer",
            self.session,
        )
        self.assertTrue(created)
        mock_resolve.assert_called_once()
        self.assertEqual(checklist["baseline_id"], "default_base")

    @patch("services.checklists.audit.log_event")
    @patch("services.checklists.grants_svc.workspace_context")
    @patch("services.checklists.baseline_defaults_svc.resolve_baseline_id", return_value="default_base")
    @patch("services.checklists.validation.persistable_valid", return_value=False)
    @patch("services.checklists.baselines_svc.list_baseline_rules")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.require_workspace_write")
    @patch("services.checklists.kv_client.batch_insert")
    @patch("services.checklists.kv_client.insert_record")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    def test_assign_idempotent_via_stig_id_only(
        self,
        mock_get_coll,
        mock_query_all,
        mock_insert,
        mock_batch,
        mock_require_write,
        mock_get_host,
        mock_get_baseline,
        mock_list_rules,
        _mock_valid,
        mock_resolve,
        mock_workspace_context,
        mock_audit,
    ):
        mock_get_host.return_value = self.host
        mock_list_rules.return_value = self.rules

        def _get_baseline(_svc, key):
            if key == "default_base":
                return {**self.baseline, "_key": "default_base"}
            return None

        mock_get_baseline.side_effect = _get_baseline
        mock_get_coll.side_effect = self.kv.get_collection
        mock_query_all.side_effect = self.kv.query_all
        mock_insert.side_effect = self.kv.insert_record
        mock_batch.side_effect = self.kv.batch_insert
        coll = {"_key": "ws1"}
        ctx = access.resolve_workspace_access(coll, self.session)
        mock_workspace_context.return_value = (coll, ctx, [])

        first, created_first = checklists_svc.assign_stig_to_host(
            self.service, "host1", {"stig_id": "Example_STIG"}, "writer", self.session
        )
        second, created_second = checklists_svc.assign_stig_to_host(
            self.service, "host1", {"stig_id": "Example_STIG"}, "writer", self.session
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first["_key"], second["_key"])
        self.assertEqual(mock_resolve.call_count, 2)

    @patch("services.checklists.delete_checklist")
    @patch("services.checklists.find_checklist")
    @patch("services.checklists.resolve_baseline_ref", return_value="old_rev")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.require_workspace_write")
    def test_unassign_stig_id_uses_shared_resolver(
        self,
        mock_require,
        mock_get_host,
        mock_resolve,
        mock_find,
        mock_delete,
    ):
        mock_get_host.return_value = self.host
        mock_find.return_value = {"_key": "cl1", "baseline_id": "old_rev"}
        result = checklists_svc.unassign_stig_from_host(
            self.service, "host1", "Example_STIG", "writer", self.session
        )
        mock_resolve.assert_called_once_with(self.service, "ws1", "Example_STIG")
        mock_find.assert_called_once_with(
            self.service, self.session, "ws1", "host1", "old_rev"
        )
        mock_delete.assert_called_once()
        self.assertEqual(result["baseline_id"], "old_rev")

    @patch("services.checklists.baselines_svc.find_baseline_by_stig")
    @patch("services.checklists.baseline_defaults_svc.resolve_baseline_id", return_value="old_rev")
    @patch("services.checklists.baselines_svc.get_baseline", return_value=None)
    def test_resolve_baseline_ref_does_not_use_catalog_latest(
        self, mock_get, mock_resolve, mock_find_latest
    ):
        bid = checklists_svc.resolve_baseline_ref(
            self.service, "ws1", "Example_STIG"
        )
        self.assertEqual(bid, "old_rev")
        mock_resolve.assert_called_once()
        mock_find_latest.assert_not_called()

    @patch("services.checklists.audit.log_event")
    @patch("services.checklists.grants_svc.workspace_context")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    def test_duplicate_host_baseline_rows_pick_acl_visible(
        self,
        mock_get_coll,
        mock_query_all,
        mock_get_host,
        mock_workspace_context,
        mock_audit,
    ):
        self.kv.checklists["cl_hidden"] = {
            "_key": "cl_hidden",
            "stig_collection_id": "ws1",
            "host_id": "host1",
            "baseline_id": "base1",
        }
        self.kv.checklists["cl_visible"] = {
            "_key": "cl_visible",
            "stig_collection_id": "ws1",
            "host_id": "host1",
            "baseline_id": "base1",
        }
        mock_get_host.return_value = self.host
        mock_get_coll.side_effect = self.kv.get_collection
        mock_query_all.side_effect = self.kv.query_all
        coll = {"_key": "ws1"}
        grants = [
            {
                "principal": "user:writer",
                "grant_role": "restricted",
                "acl_host_ids": '["host1"]',
                "acl_baseline_ids": '["base1"]',
            }
        ]
        ctx = access.resolve_workspace_access(coll, self.session, grants)
        mock_workspace_context.return_value = (coll, ctx, grants)

        with patch(
            "services.checklists.grants_svc.require_workspace_write"
        ), patch(
            "services.checklists.baselines_svc.get_baseline",
            return_value={"_key": "base1"},
        ):
            checklist, created = checklists_svc.assign_stig_to_host(
                self.service,
                "host1",
                {"baseline_id": "base1"},
                "writer",
                self.session,
            )
        self.assertFalse(created)
        self.assertEqual(checklist["_key"], "cl_hidden")
        integrity_calls = [
            c
            for c in mock_audit.call_args_list
            if c.args and c.args[0] == "data_integrity"
        ]
        self.assertEqual(len(integrity_calls), 1)

    @patch("services.checklists.list_checklists")
    @patch("services.checklists.hosts_svc.get_host")
    def test_list_checklists_for_host_uses_acl_filtered_collection_list(
        self, mock_get_host, mock_list
    ):
        mock_get_host.return_value = self.host
        mock_list.return_value = [
            {"_key": "cl1", "host_id": "host1", "baseline_id": "base1"},
            {"_key": "cl2", "host_id": "host2", "baseline_id": "base1"},
        ]
        rows = checklists_svc.list_checklists_for_host(
            self.service, "host1", self.session
        )
        mock_list.assert_called_once_with(self.service, self.session, "ws1")
        self.assertEqual([r["_key"] for r in rows], ["cl1"])


if __name__ == "__main__":
    unittest.main()
