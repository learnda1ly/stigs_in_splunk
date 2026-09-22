"""Collection import builder: batch REST, zip archives, ACL, idempotency."""

from __future__ import annotations

import io
import json
import os
import sys
import types
import unittest
import zipfile
from typing import Any, Dict
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
from importers import checklist_zip  # noqa: E402
from services import imports as imports_svc  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _session(*, write: bool = True, user: str = "alice"):
    caps = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {"authtoken": "token", "user": user, "capabilities": caps}


class TestChecklistZip(unittest.TestCase):
    def test_list_members_from_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            with open(os.path.join(FIXTURES, "minimal.ckl"), "rb") as handle:
                zf.writestr("hosts/web-01.ckl", handle.read())
            with open(os.path.join(FIXTURES, "minimal.cklb"), "rb") as handle:
                zf.writestr("hosts/db-01.cklb", handle.read())
        members = checklist_zip.list_checklist_files(buf.getvalue(), source_prefix="bundle.zip")
        self.assertEqual(len(members), 2)
        paths = sorted(path for path, _raw in members)
        self.assertEqual(paths[0], "bundle.zip/hosts/db-01.cklb")
        self.assertEqual(paths[1], "bundle.zip/hosts/web-01.ckl")


class TestCollectionImportBuilderRest(unittest.TestCase):
    def _dispatch(
        self,
        method: str,
        rest_path: str,
        *,
        body: Any = None,
        query: Dict[str, str] | None = None,
        session: Dict[str, Any] | None = None,
        raw_payload: str | None = None,
    ):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload: Dict[str, Any] = {
            "method": method,
            "session": session or _session(),
            "rest_path": rest_path,
            "query": query or [],
        }
        if raw_payload is not None:
            payload["payload"] = raw_payload
        elif body is not None:
            payload["payload"] = json.dumps(body) if isinstance(body, dict) else body
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.imports_svc, "import_checklist_batch")
    def test_collection_imports_batch(self, mock_batch):
        mock_batch.return_value = {
            "stig_collection_id": "col1",
            "results": [{"source_uri": "a.ckl", "status": "ok"}],
            "summary": {"total": 1, "succeeded": 1, "failed": 0, "created": 1, "updated": 0},
        }
        resp = self._dispatch(
            "POST",
            "stig_collections/col1/imports",
            body={"files": [{"source_uri": "a.ckl", "format": "ckl", "content": "<x/>"}]},
        )
        self.assertEqual(resp["status"], 201)
        mock_batch.assert_called_once()

    @patch.object(stig_rest_handler.imports_svc, "import_checklist_batch")
    def test_collection_imports_partial_failure_200(self, mock_batch):
        mock_batch.return_value = {
            "stig_collection_id": "col1",
            "results": [
                {"source_uri": "a.ckl", "status": "ok"},
                {"source_uri": "bad.txt", "status": "error", "error": "format"},
            ],
            "summary": {"total": 2, "succeeded": 1, "failed": 1, "created": 0, "updated": 1},
        }
        resp = self._dispatch(
            "POST",
            "stig_collections/col1/imports",
            body={"files": [{}, {}]},
        )
        self.assertEqual(resp["status"], 200)

    @patch.object(stig_rest_handler.imports_svc, "import_checklist_batch")
    def test_collection_imports_acl_403(self, mock_batch):
        mock_batch.side_effect = PermissionError("access denied")
        resp = self._dispatch(
            "POST",
            "stig_collections/col1/imports",
            body={"files": [{"source_uri": "a.ckl", "content": "x", "format": "ckl"}]},
        )
        self.assertEqual(resp["status"], 403)

    @patch.object(stig_rest_handler.imports_svc, "import_checklist_zip")
    def test_stig_imports_zip_query(self, mock_zip):
        mock_zip.return_value = {
            "stig_collection_id": "col1",
            "results": [],
            "summary": {"total": 1, "succeeded": 1, "failed": 0, "created": 1, "updated": 0},
        }
        resp = self._dispatch(
            "POST",
            "stig_imports",
            query={"format": "zip", "stig_collection_id": "col1", "source_uri": "bundle.zip"},
            raw_payload="PK\x03\x04fake",
        )
        self.assertIn(resp["status"], (200, 201))
        mock_zip.assert_called_once()


class TestImportBatchService(unittest.TestCase):
    @patch.object(imports_svc, "import_checklist_file")
    @patch.object(imports_svc, "resolve_import_workspace")
    def test_batch_mixed_success(self, mock_resolve, mock_one):
        mock_resolve.return_value = "col-default"
        mock_one.side_effect = [
            {
                "source_uri": "good.ckl",
                "format": "ckl",
                "host": {"hostname": "h1", "created": True},
                "checklists": [{"_key": "cl1", "created": True}],
                "stats": {},
                "finding_count": 2,
            },
            ValueError("checklist has no host_name"),
        ]
        out = imports_svc.import_checklist_batch(
            MagicMock(),
            _session(),
            "alice",
            "col-default",
            [
                {"source_uri": "good.ckl", "format": "ckl", "content": "<x/>"},
                {"source_uri": "bad.ckl", "format": "ckl", "content": "<y/>"},
            ],
        )
        self.assertEqual(out["summary"]["succeeded"], 1)
        self.assertEqual(out["summary"]["failed"], 1)
        self.assertEqual(out["results"][0]["status"], "ok")
        self.assertEqual(out["results"][1]["status"], "error")

    @patch.object(imports_svc, "import_checklist_file")
    @patch.object(imports_svc, "resolve_import_workspace")
    def test_batch_idempotent_updated_flag(self, mock_resolve, mock_one):
        mock_resolve.return_value = "col1"
        mock_one.return_value = {
            "source_uri": "h.ckl",
            "format": "ckl",
            "host": {"hostname": "h1", "created": False},
            "checklists": [{"_key": "cl1", "created": False}],
            "stats": {},
            "finding_count": 1,
        }
        out = imports_svc.import_checklist_batch(
            MagicMock(),
            _session(),
            "alice",
            "col1",
            [{"source_uri": "h.ckl", "format": "ckl", "content": "<x/>"}],
        )
        self.assertFalse(out["results"][0]["created"])
        self.assertEqual(out["summary"]["updated"], 1)


if __name__ == "__main__":
    unittest.main()
