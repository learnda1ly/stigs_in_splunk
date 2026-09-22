"""Cascade / block delete for stig_collection workspaces."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from models import (  # noqa: E402
    KV_STIG_ASSIGNMENT_RULES,
    KV_STIG_BASELINES,
    KV_STIG_CHECKLISTS,
    KV_STIG_COLLECTION_GRANTS,
    KV_STIG_COLLECTIONS,
    KV_STIG_HOSTS,
    KV_STIG_HOST_BASELINE_ASSIGNMENTS,
    KV_STIG_REVIEWS,
)
from services import collections as collections_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _MemKv:
    def __init__(self):
        self.store: Dict[str, Dict[str, Dict[str, Any]]] = {
            KV_STIG_COLLECTIONS: {},
            KV_STIG_HOSTS: {},
            KV_STIG_CHECKLISTS: {},
            KV_STIG_REVIEWS: {},
            KV_STIG_COLLECTION_GRANTS: {},
            KV_STIG_ASSIGNMENT_RULES: {},
            KV_STIG_HOST_BASELINE_ASSIGNMENTS: {},
            KV_STIG_BASELINES: {"base1": {"_key": "base1", "stig_id": "Example_STIG"}},
        }

    def coll(self, name: str) -> _MemColl:
        return _MemColl(self.store.setdefault(name, {}))

    def get_collection(self, _service, name: str) -> _MemColl:
        return self.coll(name)

    def query_all(
        self, coll: _MemColl, query: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        query = query or {}
        out: List[Dict[str, Any]] = []
        for rec in coll._rows.values():
            if all(rec.get(k) == v for k, v in query.items()):
                out.append(dict(rec))
        return out

    def get_by_key(self, coll: _MemColl, key: str):
        rec = coll._rows.get(key)
        return dict(rec) if rec else None

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        stored = dict(record)
        coll._rows[stored["_key"]] = stored
        return stored

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]):
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored


class TestCollectionCascadeDelete(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.kv = _MemKv()
        self.ws = "ws_delete_me"
        self.kv.store[KV_STIG_COLLECTIONS][self.ws] = {
            "_key": self.ws,
            "name": "Team A",
            "is_default": False,
        }
        self.kv.store[KV_STIG_HOSTS]["host1"] = {
            "_key": "host1",
            "stig_collection_id": self.ws,
            "hostname": "web-01",
        }
        self.kv.store[KV_STIG_CHECKLISTS]["cl1"] = {
            "_key": "cl1",
            "stig_collection_id": self.ws,
            "host_id": "host1",
            "baseline_id": "base1",
        }
        self.kv.store[KV_STIG_REVIEWS]["rev1"] = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "stig_collection_id": self.ws,
        }
        self.kv.store[KV_STIG_COLLECTION_GRANTS]["g1"] = {
            "_key": "g1",
            "stig_collection_id": self.ws,
            "principal": "user:alice",
        }
        self.kv.store[KV_STIG_ASSIGNMENT_RULES]["rule1"] = {
            "_key": "rule1",
            "target_stig_collection_id": self.ws,
        }
        self.kv.store[KV_STIG_HOST_BASELINE_ASSIGNMENTS]["ov1"] = {
            "_key": "ov1",
            "target_stig_collection_id": self.ws,
            "hostname": "web-01",
        }

    def _patch_kv(self):
        return patch.multiple(
            collections_svc,
            kv_client=MagicMock(
                get_collection=self.kv.get_collection,
                query_all=self.kv.query_all,
                get_by_key=self.kv.get_by_key,
                delete_record=self.kv.delete_record,
                insert_record=self.kv.insert_record,
                update_record=self.kv.update_record,
            ),
        )

    def test_block_delete_without_cascade(self):
        with self._patch_kv(), patch.object(collections_svc.audit, "log_event") as audit:
            with self.assertRaises(collections_svc.CollectionDeleteBlockedError) as ctx:
                collections_svc.delete_collection(
                    self.service, self.ws, "admin", cascade=False
                )
            self.assertGreater(ctx.exception.counts["hosts"], 0)
            self.assertIn(self.ws, self.kv.store[KV_STIG_COLLECTIONS])
            blocked = [
                c
                for c in audit.call_args_list
                if c.args and c.args[0] == "delete_blocked"
            ]
            self.assertEqual(len(blocked), 1)

    def test_cascade_removes_children_not_baselines(self):
        with self._patch_kv(), patch.object(collections_svc.audit, "log_event"):
            result = collections_svc.delete_collection(
                self.service, self.ws, "admin", cascade=True
            )
            self.assertTrue(result["cascade"])
            self.assertEqual(result["removed"]["hosts"], 1)
            self.assertEqual(result["removed"]["checklists"], 1)
            self.assertGreaterEqual(result["removed"]["reviews"], 1)
            self.assertEqual(result["removed"]["grants"], 1)
            self.assertNotIn(self.ws, self.kv.store[KV_STIG_COLLECTIONS])
            self.assertEqual(self.kv.store[KV_STIG_HOSTS], {})
            self.assertEqual(self.kv.store[KV_STIG_CHECKLISTS], {})
            self.assertEqual(self.kv.store[KV_STIG_REVIEWS], {})
            self.assertIn("base1", self.kv.store[KV_STIG_BASELINES])

    def test_empty_workspace_deletes_without_cascade_flag(self):
        empty = "ws_empty"
        self.kv.store[KV_STIG_COLLECTIONS][empty] = {
            "_key": empty,
            "name": "Empty",
            "is_default": False,
        }
        with self._patch_kv(), patch.object(collections_svc.audit, "log_event"):
            result = collections_svc.delete_collection(
                self.service, empty, "admin", cascade=False
            )
            self.assertFalse(result["cascade"])
            self.assertNotIn(empty, self.kv.store[KV_STIG_COLLECTIONS])


class TestCollectionDeleteRestAcl(unittest.TestCase):
    def test_rest_delete_requires_stig_admin(self):
        import json

        import stig_rest_handler  # noqa: E402

        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "DELETE",
            "session": {
                "authtoken": "token",
                "user": "bob",
                "capabilities": {"stig_read": True},
            },
            "rest_path": "stig_collections/ws1",
            "query": [],
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            with patch.object(stig_rest_handler.collections_svc, "delete_collection") as delete_mock:
                resp = handler.handle(json.dumps(payload))
                delete_mock.assert_not_called()
        self.assertEqual(resp["status"], 403)

    def test_rest_blocked_returns_409(self):
        import json
        from unittest.mock import patch

        import stig_rest_handler  # noqa: E402

        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "DELETE",
            "session": {
                "authtoken": "token",
                "user": "admin",
                "capabilities": {"stig_admin": True},
            },
            "rest_path": "stig_collections/ws1",
            "query": [],
        }
        err = collections_svc.CollectionDeleteBlockedError({"hosts": 1})
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            with patch.object(
                stig_rest_handler.collections_svc,
                "delete_collection",
                side_effect=err,
            ):
                resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 409)
        body = json.loads(resp["payload"])
        self.assertTrue(body.get("cascade_required"))


if __name__ == "__main__":
    unittest.main()
