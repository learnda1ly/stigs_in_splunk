"""Workspace-scoped baseline catalog: ACL, list filter, import scope."""

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

from importers import xccdf  # noqa: E402
from services import baselines as baselines_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _ScopeKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {},
            "stig_collection_grants": {},
            "stig_baselines": {},
            "stig_baseline_rules": {},
        }
        self._seq = 0

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

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        self._seq += 1
        key = record.get("_key") or f"gen-{self._seq}"
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def batch_insert(self, coll: _MemColl, records: List[Dict[str, Any]]) -> None:
        for rec in records:
            self.insert_record(coll, rec)


def _session(user: str, *, write: bool = False, admin: bool = False) -> Dict[str, Any]:
    caps: Dict[str, Any] = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    if admin:
        caps["stig_admin"] = True
    return {"user": user, "roles": [], "capabilities": caps}


def _patch_kv(kv: _ScopeKv):
    targets = (
        "services.baselines.kv_client",
        "services.collections.kv_client",
        "services.grants.kv_client",
        "services.baseline_library.kv_client",
    )
    patches = [patch(t, kv) for t in targets]
    for p in patches:
        p.start()
    return patches


class TestBaselineWorkspaceScope(unittest.TestCase):
    def setUp(self):
        self.kv = _ScopeKv()
        self.patches = _patch_kv(self.kv)
        self.service = MagicMock()
        self.ws_a = "ws-a"
        self.ws_b = "ws-b"
        self.kv.tables["stig_collections"][self.ws_a] = {
            "_key": self.ws_a,
            "name": "Team A",
            "access_principals": '["user:alice"]',
        }
        self.kv.tables["stig_collections"][self.ws_b] = {
            "_key": self.ws_b,
            "name": "Team B",
            "access_principals": '["user:bob"]',
        }
        self.kv.tables["stig_baselines"]["global-1"] = {
            "_key": "global-1",
            "stig_id": "Global_STIG",
            "title": "Global",
            "version": "V1R1",
        }
        self.kv.tables["stig_baselines"]["private-a"] = {
            "_key": "private-a",
            "stig_id": "Private_STIG",
            "title": "Private A",
            "version": "V1R1",
            "stig_collection_id": self.ws_a,
        }
        self.kv.tables["stig_baseline_rules"]["rule-priv"] = {
            "_key": "rule-priv",
            "baseline_id": "private-a",
            "group_id": "V-1",
            "rule_id": "SV-1",
            "ccis": '["CCI-000001"]',
        }

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_global_visible_to_all_readers(self):
        rows = baselines_svc.list_baselines_for_user(
            self.service, _session("bob")
        )
        keys = {r["_key"] for r in rows}
        self.assertIn("global-1", keys)
        self.assertNotIn("private-a", keys)

    def test_workspace_member_sees_private_catalog(self):
        rows = baselines_svc.list_baselines_for_user(
            self.service, _session("alice")
        )
        keys = {r["_key"] for r in rows}
        self.assertIn("global-1", keys)
        self.assertIn("private-a", keys)

    def test_collection_filter_includes_globals_and_workspace_rows(self):
        rows = baselines_svc.list_baselines_for_user(
            self.service,
            _session("alice"),
            stig_collection_id=self.ws_a,
        )
        keys = {r["_key"] for r in rows}
        self.assertEqual(keys, {"global-1", "private-a"})

    def test_get_hidden_baseline_returns_none(self):
        rec = baselines_svc.get_baseline_for_user(
            self.service, _session("bob"), "private-a"
        )
        self.assertIsNone(rec)

    @patch("services.baselines.audit.log_event")
    def test_import_attaches_workspace_scope(self, _audit):
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml"
        )
        with open(fixture, "rb") as handle:
            body = handle.read()
        meta, rules = xccdf.parse_xccdf(body)
        stored, created = baselines_svc.import_parsed_baseline(
            self.service,
            meta,
            rules,
            "alice",
            stig_collection_id=self.ws_a,
        )
        self.assertTrue(created)
        self.assertEqual(stored.get("stig_collection_id"), self.ws_a)

    def _dispatch(self, method: str, rest_path: str, session: Dict[str, Any]):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": {**session, "authtoken": "token"},
            "rest_path": rest_path,
            "query": [],
        }
        with patch.object(
            stig_rest_handler.kv_client, "connect", return_value=self.service
        ):
            return handler.handle(json.dumps(payload))

    def test_rest_list_hides_private_from_other_workspace(self):
        resp = self._dispatch("GET", "stig_baselines", _session("bob"))
        self.assertEqual(resp["status"], 200)
        rows = json.loads(resp["payload"])
        keys = {row["_key"] for row in rows}
        self.assertIn("global-1", keys)
        self.assertNotIn("private-a", keys)

    def test_rest_catalog_search_respects_visibility(self):
        resp = self._dispatch("GET", "stig_baselines/groups/V-1", _session("bob"))
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertEqual(body["match_count"], 0)


if __name__ == "__main__":
    unittest.main()
