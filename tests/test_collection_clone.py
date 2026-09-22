"""Clone workspace (stig_collection) REST and service."""

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
    splunk = types.ModuleType("splunk")
    splunk.persistconn = persistconn
    sys.modules["splunk"] = splunk
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application

import stig_rest_handler  # noqa: E402
from services import collection_clone as clone_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _CloneKv:
    def __init__(self) -> None:
        self._id = 0
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {
                "ws1": {
                    "_key": "ws1",
                    "name": "Source",
                    "description": "from source",
                    "access_principals": "[]",
                    "metadata": '{"env":"lab"}',
                    "default_baseline_map": '{"rhel9":"base1"}',
                    "review_requirements": '{"require_details":true}',
                },
            },
            "stig_collection_grants": {
                "g1": {
                    "_key": "g1",
                    "stig_collection_id": "ws1",
                    "principal": "user:alice",
                    "grant_role": "owner",
                    "acl_host_ids": "[]",
                    "acl_baseline_ids": "[]",
                    "acl_labels": "[]",
                },
            },
            "stig_hosts": {
                "h1": {
                    "_key": "h1",
                    "stig_collection_id": "ws1",
                    "hostname": "alpha",
                    "label_ids": '["lbl1"]',
                },
            },
            "stig_labels": {
                "lbl1": {
                    "_key": "lbl1",
                    "stig_collection_id": "ws1",
                    "name": "Prod",
                    "color": "blue",
                },
            },
            "stig_checklists": {
                "cl1": {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                    "title": "RHEL",
                },
            },
            "stig_reviews": {
                "r1": {
                    "_key": "r1",
                    "checklist_id": "cl1",
                    "stig_collection_id": "ws1",
                    "rule_id": "V-1",
                    "status": "open",
                    "finding_details": "detail",
                },
            },
            "stig_baselines": {},
            "stig_baseline_rules": {},
            "stig_assignment_rules": {},
            "stig_host_baseline_assignments": {},
        }

    def next_id(self) -> str:
        self._id += 1
        return f"n{self._id}"

    def get_collection(self, _service, name: str) -> _MemColl:
        if name not in self.tables:
            self.tables[name] = {}
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

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        key = record.get("_key") or self.next_id()
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)


def _session(user: str = "alice", *, write: bool = True) -> Dict[str, Any]:
    caps = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {"user": user, "roles": [], "capabilities": caps}


def _patch_kv(kv: _CloneKv):
    modules = (
        "services.collections.kv_client",
        "services.grants.kv_client",
        "services.collection_clone.kv_client",
        "services.collection_metadata.kv_client",
    )
    patches = []
    for mod in modules:
        patches.append(patch(f"{mod}.get_collection", side_effect=kv.get_collection))
        patches.append(patch(f"{mod}.query_all", side_effect=kv.query_all))
        patches.append(patch(f"{mod}.get_by_key", side_effect=kv.get_by_key))
        patches.append(patch(f"{mod}.insert_record", side_effect=kv.insert_record))
        patches.append(patch(f"{mod}.update_record", side_effect=kv.update_record))
        patches.append(patch(f"{mod}.delete_record", side_effect=kv.delete_record))
    patches.append(patch("services.collections.new_id", side_effect=kv.next_id))
    patches.append(patch("services.collection_clone.new_id", side_effect=kv.next_id))
    patches.append(patch("services.collections.kv_record", side_effect=lambda r: r))
    patches.append(patch("services.collection_clone.kv_record", side_effect=lambda r: r))
    return patches


class TestCloneOptions(unittest.TestCase):
    def test_defaults(self):
        opts = clone_svc.parse_clone_options({})
        self.assertTrue(opts["copy_hosts"])
        self.assertTrue(opts["copy_reviews"])
        self.assertFalse(opts["copy_grants"])

    def test_shallow_clone_flags(self):
        opts = clone_svc.parse_clone_options(
            {"copy_hosts": True, "copy_checklists": False, "copy_reviews": True}
        )
        self.assertFalse(opts["copy_checklists"])
        self.assertFalse(opts["copy_reviews"])


class TestCollectionCloneService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _CloneKv()
        self.patches = _patch_kv(self.kv)
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()

    @patch("services.collection_clone.audit.log_event")
    @patch("services.collections.audit.log_event")
    @patch("services.collections.find_default_collection", return_value=None)
    def test_deep_clone_remaps_ids(self, _def, _audit_create, mock_audit) -> None:
        alice = _session()
        with patch(
            "services.collection_clone.collections_svc.get_collection",
            side_effect=lambda _s, cid: self.kv.tables["stig_collections"].get(cid),
        ), patch(
            "services.collections.kv_client.get_collection",
            side_effect=self.kv.get_collection,
        ), patch(
            "services.collections.kv_client.query_all",
            side_effect=self.kv.query_all,
        ), patch(
            "services.collections.kv_client.get_by_key",
            side_effect=self.kv.get_by_key,
        ), patch(
            "services.collections.kv_client.insert_record",
            side_effect=self.kv.insert_record,
        ), patch(
            "services.collections.kv_client.update_record",
            side_effect=self.kv.update_record,
        ), patch(
            "services.collections.kv_client.delete_record",
            side_effect=self.kv.delete_record,
        ):
            result = clone_svc.clone_collection(
                self.service,
                "ws1",
                {"name": "Cloned"},
                "alice",
                alice,
            )
        dest_id = result["stig_collection_id"]
        self.assertNotEqual(dest_id, "ws1")
        hosts = [
            h
            for h in self.kv.tables["stig_hosts"].values()
            if h.get("stig_collection_id") == dest_id
        ]
        self.assertEqual(len(hosts), 1)
        new_host = hosts[0]["_key"]
        self.assertNotEqual(new_host, "h1")
        checklists = [
            c
            for c in self.kv.tables["stig_checklists"].values()
            if c.get("stig_collection_id") == dest_id
        ]
        self.assertEqual(checklists[0]["host_id"], new_host)
        reviews = [
            r
            for r in self.kv.tables["stig_reviews"].values()
            if r.get("checklist_id") == checklists[0]["_key"]
        ]
        self.assertEqual(reviews[0]["status"], "open")
        self.assertEqual(result["summary"]["hosts"], 1)
        clone_calls = [c for c in mock_audit.call_args_list if c.args[0] == "clone"]
        self.assertEqual(len(clone_calls), 1)

    @patch("services.collection_clone.audit.log_event")
    @patch("services.collections.audit.log_event")
    @patch("services.collections.find_default_collection", return_value=None)
    def test_without_reviews(self, _def, _a, _b) -> None:
        alice = _session()
        with patch(
            "services.collection_clone.collections_svc.get_collection",
            side_effect=lambda _s, cid: self.kv.tables["stig_collections"].get(cid),
        ), patch("services.collections.kv_client.get_collection", side_effect=self.kv.get_collection), patch(
            "services.collections.kv_client.query_all", side_effect=self.kv.query_all
        ), patch(
            "services.collections.kv_client.get_by_key", side_effect=self.kv.get_by_key
        ), patch(
            "services.collections.kv_client.insert_record", side_effect=self.kv.insert_record
        ), patch(
            "services.collections.kv_client.update_record", side_effect=self.kv.update_record
        ), patch(
            "services.collections.kv_client.delete_record", side_effect=self.kv.delete_record
        ):
            result = clone_svc.clone_collection(
                self.service,
                "ws1",
                {"name": "No reviews", "copy_reviews": False},
                "alice",
                alice,
            )
        dest_id = result["stig_collection_id"]
        reviews = [
            r
            for r in self.kv.tables["stig_reviews"].values()
            if r.get("stig_collection_id") == dest_id
        ]
        self.assertEqual(reviews, [])
        self.assertEqual(result["summary"]["checklists"], 1)

    def test_acl_denied_without_write_cap(self) -> None:
        reader = _session(write=False)
        with self.assertRaises(PermissionError):
            clone_svc.clone_collection(
                self.service,
                "ws1",
                {"name": "x"},
                "alice",
                reader,
            )

    def test_acl_denied_without_source_read(self) -> None:
        alice = _session()
        del self.kv.tables["stig_collection_grants"]["g1"]
        self.kv.tables["stig_collections"]["ws1"]["access_principals"] = (
            '["user:someone_else"]'
        )
        with self.assertRaises(PermissionError):
            clone_svc.clone_collection(
                self.service,
                "ws1",
                {"name": "x"},
                "alice",
                alice,
            )


class TestCollectionCloneRest(unittest.TestCase):
    @patch.object(clone_svc, "clone_collection")
    def test_rest_clone_route(self, mock_clone) -> None:
        mock_clone.return_value = {
            "stig_collection_id": "ws9",
            "summary": {"hosts": 0},
        }
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": {
                "authtoken": "t",
                "user": "alice",
                "capabilities": {"stig_write": True},
            },
            "rest_path": "stig_collections/ws1/clone",
            "payload": json.dumps({"name": "Copy"}),
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 201)
        mock_clone.assert_called_once()


if __name__ == "__main__":
    unittest.main()
