"""Collection archive CKL/CKLB export (workspace-scoped bulk zip)."""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import types
import unittest
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import access  # noqa: E402
from services import checklists as checklists_svc  # noqa: E402

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


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _MemKv:
    def __init__(self):
        self.checklists: Dict[str, Dict[str, Any]] = {}
        self.reviews: Dict[str, Dict[str, Any]] = {}

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

    def get_by_key(self, coll: _MemColl, key: str) -> Dict[str, Any] | None:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None


def _read_session(user: str = "alice") -> Dict[str, Any]:
    return {
        "authtoken": "token",
        "user": user,
        "roles": [],
        "capabilities": {"stig_read": True, "stig_write": True},
    }


def _wire_kv_patches(kv: _MemKv):
    return (
        patch("services.checklists.kv_client.get_collection", side_effect=kv.get_collection),
        patch("services.checklists.kv_client.query_all", side_effect=kv.query_all),
        patch("services.checklists.kv_client.get_by_key", side_effect=kv.get_by_key),
    )


class TestCollectionArchiveExport(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.session = _read_session()
        self.kv = _MemKv()
        self.ws = {
            "_key": "ws1",
            "name": "Lab Workspace",
            "access_principals": '["user:alice"]',
        }
        self.host_a = {
            "_key": "host_a",
            "stig_collection_id": "ws1",
            "hostname": "web-01.lab",
        }
        self.host_b = {
            "_key": "host_b",
            "stig_collection_id": "ws1",
            "hostname": "db-01.lab",
        }
        self.baseline = {
            "_key": "base1",
            "stig_id": "RHEL_8_STIG",
            "title": "RHEL 8 STIG",
            "version": "V2R6",
        }
        self.rules = [
            {
                "group_id": "V-1",
                "rule_id": "SV-1",
                "rule_title": "Rule one",
                "ccis": ["CCI-000366"],
            }
        ]
        self.kv.checklists = {
            "cl1": {
                "_key": "cl1",
                "stig_collection_id": "ws1",
                "host_id": "host_a",
                "baseline_id": "base1",
                "title": "t1",
                "target_data": "{}",
            },
            "cl2": {
                "_key": "cl2",
                "stig_collection_id": "ws1",
                "host_id": "host_b",
                "baseline_id": "base1",
                "title": "t2",
                "target_data": "{}",
            },
        }
        self.kv.reviews = {
            "rv1": {
                "_key": "rv1",
                "checklist_id": "cl1",
                "group_id": "V-1",
                "rule_id": "SV-1",
                "status": "open",
                "finding_details": "detail",
                "comments": "",
            }
        }

    @patch("services.checklists.export_checklist_file")
    @patch("services.checklists.checklist_ids_for_collection_export")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    def test_workspace_bulk_zip_filenames(
        self,
        get_coll,
        _grants,
        mock_ids,
        mock_file,
    ):
        get_coll.return_value = self.ws
        mock_ids.return_value = ["cl1", "cl2"]

        def _file(_svc, key, fmt, _session):
            if key == "cl1":
                return ("{}", "web-01.lab_RHEL_8_STIG_V2R6.cklb")
            return ("{}", "db-01.lab_RHEL_8_STIG_V2R6.cklb")

        mock_file.side_effect = _file

        result = checklists_svc.export_collection_archive(
            self.service, "ws1", "cklb", self.session
        )

        self.assertEqual(result["format"], "cklb")
        self.assertEqual(result["count"], 2)
        self.assertEqual(
            result["filename"],
            "stig-archive-Lab_Workspace-cklb.zip",
        )
        self.assertEqual(
            sorted(result["files"]),
            [
                "db-01.lab_RHEL_8_STIG_V2R6.cklb",
                "web-01.lab_RHEL_8_STIG_V2R6.cklb",
            ],
        )
        raw = base64.b64decode(result["content_base64"])
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            names = set(archive.namelist())
        self.assertEqual(names, set(result["files"]))

    @patch("services.checklists.baselines_svc.list_baseline_rules")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    def test_archive_zip_members_are_valid_ckl_and_cklb(
        self,
        get_coll,
        _grants,
        mock_get_host,
        mock_get_baseline,
        mock_rules,
    ):
        get_coll.return_value = self.ws
        self.kv.checklists = {"cl1": self.kv.checklists["cl1"]}
        mock_get_baseline.return_value = self.baseline
        mock_rules.return_value = self.rules

        def _host(_svc, host_id, _session):
            return {"host_a": self.host_a}.get(host_id)

        mock_get_host.side_effect = _host

        patches = _wire_kv_patches(self.kv)
        for p in patches:
            p.start()
        try:
            for fmt, parser in (("ckl", ET.fromstring), ("cklb", json.loads)):
                result = checklists_svc.export_collection_archive(
                    self.service, "ws1", fmt, self.session
                )
                self.assertEqual(result["count"], 1)
                raw = base64.b64decode(result["content_base64"])
                with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
                    self.assertEqual(len(archive.namelist()), 1)
                    body = archive.read(archive.namelist()[0]).decode("utf-8")
                root = parser(body)
                if fmt == "ckl":
                    self.assertEqual(root.tag, "CHECKLIST")
                    self.assertIsNotNone(root.find(".//STATUS"))
                else:
                    self.assertIn("stigs", root)
                    self.assertEqual(root["mode"], 2)
        finally:
            for p in patches:
                p.stop()

    @patch("services.checklists.checklist_ids_for_collection_export", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    def test_empty_workspace_raises(self, _grants, get_coll, _ids):
        get_coll.return_value = self.ws
        with self.assertRaises(ValueError) as ctx:
            checklists_svc.export_collection_archive(
                self.service, "ws1", "ckl", self.session
            )
        self.assertIn("no checklists", str(ctx.exception).lower())

    @patch("services.checklists.collections_svc.get_collection")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    def test_rest_archive_empty_workspace_400(self, _grants, get_coll):
        get_coll.return_value = self.ws
        patches = _wire_kv_patches(self.kv)
        self.kv.checklists = {}
        for p in patches:
            p.start()
        try:
            handler = stig_rest_handler.StigRestHandler("", "")
            payload = {
                "method": "POST",
                "session": _read_session(),
                "rest_path": "stig_collections/ws1/archive/cklb",
            }
            with patch.object(
                stig_rest_handler.kv_client, "connect", return_value=MagicMock()
            ):
                resp = handler.handle(json.dumps(payload))
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(resp["status"], 400)
        body = json.loads(resp["payload"])
        self.assertIn("error", body)
        self.assertIn("no checklists", body["error"].lower())

    @patch.object(stig_rest_handler.checklists_svc, "export_collection_archive")
    def test_rest_archive_ckl_route(self, mock_export):
        mock_export.return_value = {
            "format": "ckl",
            "filename": "stig-archive-ws1-ckl.zip",
            "count": 1,
            "files": ["h.ckl"],
            "content_base64": base64.b64encode(b"zip").decode("ascii"),
        }
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": _read_session(),
            "rest_path": "stig_collections/ws1/archive/ckl",
            "query": {"host_id": "host_a"},
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertEqual(body["format"], "ckl")
        mock_export.assert_called_once()

    @patch.object(stig_rest_handler.checklists_svc, "export_collection_archive")
    def test_rest_archive_not_found(self, mock_export):
        mock_export.side_effect = KeyError("secret")
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": _read_session(),
            "rest_path": "stig_collections/secret/archive/cklb",
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 404)

    def test_archive_acl_denied_service_and_rest(self):
        private_ws = {
            "_key": "secret",
            "name": "Private",
            "access_principals": '["user:alice"]',
        }
        with patch(
            "services.checklists.collections_svc.get_collection",
            return_value=private_ws,
        ):
            with patch("services.checklists.grants_svc.query_grants", return_value=[]):
                with self.assertRaises(KeyError):
                    checklists_svc.export_collection_archive(
                        self.service,
                        "secret",
                        "ckl",
                        _read_session("bob"),
                    )
                with self.assertRaises(KeyError):
                    checklists_svc.export_checklists_bulk(
                        self.service,
                        None,
                        "ckl",
                        _read_session("bob"),
                        stig_collection_id="secret",
                    )

        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": _read_session("bob"),
            "rest_path": "stig_collections/secret/archive/ckl",
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            with patch.object(
                stig_rest_handler.collections_svc,
                "get_collection",
                return_value=private_ws,
            ):
                with patch.object(
                    stig_rest_handler.grants_svc, "query_grants", return_value=[]
                ):
                    resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 404)
        body = json.loads(resp["payload"])
        self.assertNotIn("content_base64", body)

        bulk_payload = {
            "method": "POST",
            "session": _read_session("bob"),
            "rest_path": "stig_checklists/export_bulk",
            "payload": json.dumps({"stig_collection_id": "secret", "format": "ckl"}),
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            with patch.object(
                stig_rest_handler.collections_svc,
                "get_collection",
                return_value=private_ws,
            ):
                with patch.object(
                    stig_rest_handler.grants_svc, "query_grants", return_value=[]
                ):
                    bulk_resp = handler.handle(json.dumps(bulk_payload))
        self.assertEqual(bulk_resp["status"], 404)

    @patch.object(stig_rest_handler.checklists_svc, "export_checklists_bulk")
    def test_export_bulk_accepts_workspace_id(self, mock_bulk):
        mock_bulk.return_value = {"format": "cklb", "count": 2}
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": _read_session(),
            "rest_path": "stig_checklists/export_bulk",
            "payload": json.dumps(
                {"stig_collection_id": "ws1", "format": "cklb", "host_id": "host_a"}
            ),
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            handler.handle(json.dumps(payload))
        mock_bulk.assert_called_once()

    def test_checklist_ids_respect_baseline_filter(self):
        with patch.object(checklists_svc, "_access_context") as mock_ctx:
            mock_ctx.return_value = access.WorkspaceAccess(
                can_read=True,
                can_write=True,
                manage_grants=False,
                edit_collection=False,
                edit_access_principals=False,
                grant_role="member",
                acl_host_ids=None,
                acl_baseline_ids=None,
                acl_label_ids=None,
            )
            with patch.object(checklists_svc, "_require_workspace_export_access"):
                with patch("services.checklists.kv_client.get_collection") as get_coll:
                    get_coll.return_value = _MemColl(self.kv.checklists)
                    with patch(
                        "services.checklists.kv_client.query_all",
                        side_effect=self.kv.query_all,
                    ):
                        ids = checklists_svc.checklist_ids_for_collection_export(
                            self.service,
                            "ws1",
                            self.session,
                            baseline_id="base1",
                            host_id="host_b",
                        )
        self.assertEqual(ids, ["cl2"])

    @patch("services.checklists.export_checklist_file")
    def test_bulk_zip_collision_suffix(self, mock_file):
        shared = "same_host_RHEL_8_STIG_V2R6.cklb"
        mock_file.side_effect = [
            ('{"a":1}', shared),
            ('{"a":2}', shared),
        ]
        result = checklists_svc.export_checklists_bulk(
            self.service,
            ["cl1", "cl2"],
            "cklb",
            self.session,
        )
        self.assertEqual(
            sorted(result["files"]),
            [shared, "same_host_RHEL_8_STIG_V2R6_2.cklb"],
        )
        raw = base64.b64decode(result["content_base64"])
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            self.assertEqual(len(archive.namelist()), 2)


if __name__ == "__main__":
    unittest.main()
