"""REST KV connect identity: no admin trusted fallback; workspace ACL via REST."""

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

import kv_client  # noqa: E402
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
            "stig_hosts": {},
            "stig_checklists": {},
            "stig_reviews": {},
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

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        key = record.get("_key") or f"gen-{len(coll._rows) + 1}"
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored


def _stig_user_session(
    user: str, *, write: bool = False
) -> Dict[str, Any]:
    caps: Dict[str, Any] = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {
        "user": user,
        "roles": ["stig_user"],
        "capabilities": caps,
        "authtoken": f"token-{user}",
    }


def _patch_kv(kv: _ScopeKv):
    targets = (
        "services.baselines.kv_client",
        "services.collections.kv_client",
        "services.grants.kv_client",
        "services.baseline_library.kv_client",
        "services.checklists.kv_client",
        "services.hosts.kv_client",
        "services.baseline_defaults.kv_client",
    )
    patches = [patch(t, kv) for t in targets]
    for p in patches:
        p.start()
    return patches


class TestKvConnectIdentity(unittest.TestCase):
    def test_never_requests_admin_trusted_session(self):
        trusted_users: List[str] = []

        def fake_trusted(user: str):
            trusted_users.append(user)
            return None

        session = _stig_user_session("carol")
        auth_mod = types.ModuleType("splunk.auth")
        auth_mod.getSessionKeyForTrustedUser = fake_trusted
        sys.modules["splunk.auth"] = auth_mod

        with patch.object(
            stig_rest_handler.kv_client, "connect", return_value=MagicMock()
        ) as connect:
            stig_rest_handler._kv_connect(session)
            connect.assert_called_once_with("token-carol")
        self.assertEqual(trusted_users, ["carol"])

    def test_caller_token_used_when_admin_trusted_would_succeed(self):
        def fake_trusted(user: str):
            if user == "admin":
                return "admin-session-key"
            return None

        session = _stig_user_session("carol")
        auth_mod = types.ModuleType("splunk.auth")
        auth_mod.getSessionKeyForTrustedUser = fake_trusted
        sys.modules["splunk.auth"] = auth_mod

        with patch.object(
            stig_rest_handler.kv_client, "connect", return_value=MagicMock()
        ) as connect:
            stig_rest_handler._kv_connect(session)
            connect.assert_called_once_with("token-carol")

    def test_kv_unreachable_as_caller_raises_permission_error(self):
        def fake_trusted(_user: str):
            return None

        def fake_connect(key: str):
            if key == "admin-session-key":
                return MagicMock(name="admin_kv")
            raise kv_client.KvError("forbidden", status=403)

        session = _stig_user_session("carol")
        auth_mod = types.ModuleType("splunk.auth")
        auth_mod.getSessionKeyForTrustedUser = fake_trusted
        sys.modules["splunk.auth"] = auth_mod

        with patch.object(
            stig_rest_handler.kv_client, "connect", side_effect=fake_connect
        ):
            with self.assertRaises(PermissionError):
                stig_rest_handler._kv_connect(session)


class TestStigUserWorkspaceRestAcl(unittest.TestCase):
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
        self.kv.tables["stig_baselines"]["private-a"] = {
            "_key": "private-a",
            "stig_id": "Private_STIG",
            "title": "Private A",
            "version": "V1R1",
            "stig_collection_id": self.ws_a,
        }
        self.kv.tables["stig_checklists"]["cl-a"] = {
            "_key": "cl-a",
            "stig_collection_id": self.ws_a,
            "host_id": "host-a",
            "baseline_id": "private-a",
        }

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _dispatch(
        self,
        method: str,
        rest_path: str,
        session: Dict[str, Any],
        query=None,
        body: bytes = b"",
    ):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": session,
            "rest_path": rest_path,
            "query": query or [],
        }
        if body:
            payload["payload"] = body.decode("utf-8")

        def fake_trusted(user: str):
            if user == "admin":
                return "admin-session-key"
            return None

        auth_mod = types.ModuleType("splunk.auth")
        auth_mod.getSessionKeyForTrustedUser = fake_trusted
        sys.modules["splunk.auth"] = auth_mod

        with patch.object(
            stig_rest_handler.kv_client, "connect", return_value=self.service
        ) as connect:
            resp = handler.handle(json.dumps(payload))
        connect.assert_called_with(session["authtoken"])
        return resp

    def test_stig_user_cannot_read_foreign_workspace_baseline_via_rest(self):
        resp = self._dispatch(
            "GET",
            "stig_baselines/private-a",
            _stig_user_session("bob"),
        )
        self.assertEqual(resp["status"], 404)

    def test_stig_user_cannot_read_foreign_workspace_checklist_via_rest(self):
        resp = self._dispatch(
            "GET",
            "stig_checklists/cl-a",
            _stig_user_session("bob"),
        )
        self.assertEqual(resp["status"], 404)

    def test_stig_user_cannot_write_foreign_workspace_via_rest_import(self):
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml"
        )
        with open(fixture, "rb") as handle:
            body = handle.read()
        resp = self._dispatch(
            "POST",
            "stig_baselines/import",
            _stig_user_session("bob", write=True),
            query=[["stig_collection_id", self.ws_a], ["format", "xccdf"]],
            body=body,
        )
        self.assertEqual(resp["status"], 403)

    def test_rest_kv_failure_returns_403_not_admin_elevation(self):
        session = _stig_user_session("bob")

        def fake_trusted(user: str):
            if user == "admin":
                return "admin-session-key"
            return None

        def fake_connect(key: str):
            if key == "admin-session-key":
                return MagicMock(name="admin_kv")
            raise kv_client.KvError("forbidden", status=403)

        auth_mod = types.ModuleType("splunk.auth")
        auth_mod.getSessionKeyForTrustedUser = fake_trusted
        sys.modules["splunk.auth"] = auth_mod

        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": session,
            "rest_path": "stig_baselines",
        }
        with patch.object(
            stig_rest_handler.kv_client, "connect", side_effect=fake_connect
        ):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)


if __name__ == "__main__":
    unittest.main()
