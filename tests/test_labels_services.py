"""Workspace label CRUD and host assignment (services.labels)."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import labels as labels_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _LabelKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {
                "ws1": {"_key": "ws1", "name": "Lab", "access_principals": "[]"}
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
                }
            },
            "stig_labels": {},
            "stig_hosts": {
                "h1": {
                    "_key": "h1",
                    "stig_collection_id": "ws1",
                    "hostname": "host-a",
                    "label_ids": "[]",
                }
            },
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

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        key = record["_key"]
        coll._rows[key] = dict(record)
        return dict(record)

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)


def _session(write: bool = False) -> Dict[str, Any]:
    caps = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {"user": "alice", "roles": [], "capabilities": caps}


class TestLabelsServices(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _LabelKv()
        modules = (
            "services.labels.kv_client",
            "services.grants.kv_client",
        )
        self.patches = []
        for mod in modules:
            self.patches.append(
                patch(f"{mod}.get_collection", side_effect=self.kv.get_collection)
            )
            self.patches.append(
                patch(f"{mod}.query_all", side_effect=self.kv.query_all)
            )
            self.patches.append(
                patch(f"{mod}.get_by_key", side_effect=self.kv.get_by_key)
            )
        self.patches.append(
            patch(
                "services.labels.kv_client.insert_record",
                side_effect=self.kv.insert_record,
            )
        )
        self.patches.append(
            patch(
                "services.labels.kv_client.update_record",
                side_effect=self.kv.update_record,
            )
        )
        self.patches.append(
            patch(
                "services.labels.kv_client.delete_record",
                side_effect=self.kv.delete_record,
            )
        )
        self.patches.append(patch("services.labels.audit.log_event"))
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()

    def test_create_and_list_labels(self) -> None:
        created = labels_svc.create_label(
            self.service,
            "ws1",
            {"name": "Production"},
            "alice",
            _session(write=True),
        )
        self.assertTrue(created.get("_key"))
        rows = labels_svc.list_labels(self.service, "ws1", _session())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Production")

    def test_assign_label_to_hosts(self) -> None:
        lbl = labels_svc.create_label(
            self.service,
            "ws1",
            {"name": "Prod"},
            "alice",
            _session(write=True),
        )
        result = labels_svc.assign_label_to_hosts(
            self.service,
            "ws1",
            lbl["_key"],
            {"host_ids": ["h1"]},
            "alice",
            _session(write=True),
        )
        self.assertEqual(result["updated_hosts"], 1)
        host = self.kv.tables["stig_hosts"]["h1"]
        self.assertIn(lbl["_key"], host["label_ids"])

    def test_assign_skips_unknown_host_ids(self) -> None:
        lbl = labels_svc.create_label(
            self.service,
            "ws1",
            {"name": "Prod"},
            "alice",
            _session(write=True),
        )
        result = labels_svc.assign_label_to_hosts(
            self.service,
            "ws1",
            lbl["_key"],
            {"host_ids": ["missing-host"]},
            "alice",
            _session(write=True),
        )
        self.assertEqual(result["updated_hosts"], 0)

    def test_delete_label_strips_host_references(self) -> None:
        lbl = labels_svc.create_label(
            self.service,
            "ws1",
            {"name": "Temp"},
            "alice",
            _session(write=True),
        )
        labels_svc.assign_label_to_hosts(
            self.service,
            "ws1",
            lbl["_key"],
            {"host_ids": ["h1"]},
            "alice",
            _session(write=True),
        )
        labels_svc.delete_label(
            self.service, "ws1", lbl["_key"], "alice", _session(write=True)
        )
        host = self.kv.tables["stig_hosts"]["h1"]
        self.assertEqual(host["label_ids"], "[]")

    def test_delete_label_prunes_grant_acl_labels(self) -> None:
        lbl = labels_svc.create_label(
            self.service,
            "ws1",
            {"name": "Scoped"},
            "alice",
            _session(write=True),
        )
        self.kv.tables["stig_collection_grants"]["g1"]["acl_labels"] = (
            '["' + lbl["_key"] + '"]'
        )
        labels_svc.delete_label(
            self.service, "ws1", lbl["_key"], "alice", _session(write=True)
        )
        grant = self.kv.tables["stig_collection_grants"]["g1"]
        self.assertEqual(grant["acl_labels"], "[]")


if __name__ == "__main__":
    unittest.main()
