"""Bulk host transfer between workspaces."""

from __future__ import annotations

import json
import os
import sys
import types
import unittest
from typing import Any, Dict, List, Optional
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
    persistconn.application = application
    splunk = types.ModuleType("splunk")
    splunk.persistconn = persistconn
    sys.modules["splunk"] = splunk
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application

import stig_rest_handler  # noqa: E402
from services import collection_transfer as transfer_svc  # noqa: E402
from services import hosts as hosts_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _TransferKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {
                "ws1": {"_key": "ws1", "name": "Source", "access_principals": "[]"},
                "ws2": {"_key": "ws2", "name": "Dest", "access_principals": "[]"},
            },
            "stig_collection_grants": {},
            "stig_hosts": {
                "h1": {
                    "_key": "h1",
                    "stig_collection_id": "ws1",
                    "hostname": "alpha",
                    "label_ids": '["lbl1"]',
                },
                "h2": {
                    "_key": "h2",
                    "stig_collection_id": "ws1",
                    "hostname": "beta",
                    "label_ids": "[]",
                },
            },
            "stig_labels": {
                "lbl1": {"_key": "lbl1", "stig_collection_id": "ws1", "name": "Prod"},
                "lbl2": {"_key": "lbl2", "stig_collection_id": "ws2", "name": "Prod"},
            },
            "stig_checklists": {
                "cl1": {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                },
            },
            "stig_reviews": {
                "r1": {
                    "_key": "r1",
                    "checklist_id": "cl1",
                    "status": "open",
                },
            },
            "stig_baselines": {},
            "stig_baseline_rules": {},
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables[name])

    def query_all(
        self, coll: _MemColl, query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query = query or {}
        return [
            dict(rec)
            for rec in coll._rows.values()
            if all(rec.get(k) == v for k, v in query.items())
        ]

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored


def _session(user: str = "alice", *, write: bool = True) -> Dict[str, Any]:
    caps = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {"user": user, "roles": [], "capabilities": caps}


def _patch_kv(kv: _TransferKv):
    modules = (
        "services.collections.kv_client",
        "services.grants.kv_client",
        "services.hosts.kv_client",
        "services.labels.kv_client",
        "services.checklists.kv_client",
    )
    patches = []
    for mod in modules:
        patches.append(patch(f"{mod}.get_collection", side_effect=kv.get_collection))
        patches.append(patch(f"{mod}.query_all", side_effect=kv.query_all))
        patches.append(patch(f"{mod}.get_by_key", side_effect=kv.get_by_key))
    patches.append(
        patch("services.hosts.kv_client.update_record", side_effect=kv.update_record)
    )
    patches.append(patch("services.hosts.kv_record", side_effect=lambda r: r))
    return patches


class TestCollectionTransferService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _TransferKv()
        self.patches = _patch_kv(self.kv)
        for p in self.patches:
            p.start()
        self.kv.tables["stig_collection_grants"]["g1"] = {
            "_key": "g1",
            "stig_collection_id": "ws1",
            "principal": "user:alice",
            "grant_role": "owner",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }
        self.kv.tables["stig_collection_grants"]["g2"] = {
            "_key": "g2",
            "stig_collection_id": "ws2",
            "principal": "user:alice",
            "grant_role": "owner",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()

    @patch("services.hosts.audit.log_event")
    def test_bulk_move_updates_host_and_checklist(self, mock_audit) -> None:
        alice = _session()
        with patch("services.collection_transfer.collections_svc.get_collection") as mock_get:
            mock_get.side_effect = lambda _s, cid: self.kv.tables["stig_collections"].get(cid)
            result = transfer_svc.export_hosts_to_collection(
                self.service,
                "ws1",
                "ws2",
                {"host_ids": ["h1", "h2"]},
                "alice",
                alice,
            )
        self.assertEqual(result["summary"]["moved"], 2)
        self.assertEqual(
            self.kv.tables["stig_hosts"]["h1"]["stig_collection_id"], "ws2"
        )
        self.assertEqual(
            self.kv.tables["stig_checklists"]["cl1"]["stig_collection_id"], "ws2"
        )
        transfer_calls = [
            c
            for c in mock_audit.call_args_list
            if c.args and c.args[0] == "transfer"
        ]
        self.assertEqual(len(transfer_calls), 2)
        self.assertEqual(transfer_calls[0].args[2], "h1")

    @patch("services.hosts.audit.log_event")
    def test_single_patch_move_audits_transfer(self, mock_audit) -> None:
        alice = _session()
        hosts_svc.update_host(
            self.service,
            "h1",
            {"stig_collection_id": "ws2"},
            "alice",
            alice,
        )
        transfer_calls = [
            c for c in mock_audit.call_args_list if c.args[0] == "transfer"
        ]
        self.assertEqual(len(transfer_calls), 1)
        details = transfer_calls[0].args[4]
        self.assertEqual(details["from_stig_collection_id"], "ws1")
        self.assertEqual(details["to_stig_collection_id"], "ws2")
        self.assertEqual(details["checklists_moved"], 1)

    @patch("services.hosts.audit.log_event")
    def test_labels_sanitized_on_move(self, mock_audit) -> None:
        alice = _session()
        hosts_svc.transfer_host_to_collection(
            self.service, "h1", "ws1", "ws2", "alice", alice
        )
        labels = hosts_svc._normalize_label_ids(
            self.kv.tables["stig_hosts"]["h1"].get("label_ids")
        )
        self.assertEqual(labels, [])

    def test_acl_deny_destination(self) -> None:
        alice = _session()
        del self.kv.tables["stig_collection_grants"]["g2"]
        self.kv.tables["stig_collections"]["ws2"]["access_principals"] = (
            '["user:someone_else"]'
        )
        with patch("services.collection_transfer.collections_svc.get_collection") as mock_get:
            mock_get.side_effect = lambda _s, cid: self.kv.tables["stig_collections"].get(cid)
            with self.assertRaises(PermissionError):
                transfer_svc.export_hosts_to_collection(
                    self.service,
                    "ws1",
                    "ws2",
                    {"host_ids": ["h1"]},
                    "alice",
                    alice,
                )

    @patch.object(transfer_svc, "export_hosts_to_collection")
    def test_rest_route(self, mock_export) -> None:
        mock_export.return_value = {
            "from_stig_collection_id": "ws1",
            "to_stig_collection_id": "ws2",
            "summary": {"moved": 1, "failed": 0, "skipped": 0},
            "results": [],
        }
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": {"authtoken": "t", "user": "alice", "capabilities": {"stig_write": True}},
            "rest_path": "stig_collections/ws1/export-to/ws2",
            "payload": json.dumps({"host_ids": ["h1"]}),
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 201)
        mock_export.assert_called_once()


if __name__ == "__main__":
    unittest.main()
