"""XCCDF TestResult zip archive ingest (format=zip / xccdf-results-zip)."""

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
from importers import xccdf_results_zip  # noqa: E402
from services import imports as imports_svc  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
RESULTS_XML = os.path.join(FIXTURES, "minimal_xccdf_results.xml")


def _session(*, write: bool = True, user: str = "alice"):
    caps = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {"authtoken": "token", "user": user, "capabilities": caps}


def _results_zip(*members: tuple[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        with open(RESULTS_XML, "rb") as handle:
            default = handle.read()
        for path, variant in members:
            if variant == "default":
                zf.writestr(path, default)
            elif variant == "baseline":
                zf.writestr(path, b'<?xml version="1.0"?><Benchmark id="x"/>')
            else:
                zf.writestr(path, variant.encode("utf-8"))
    return buf.getvalue()


class TestXccdfResultsZipWalker(unittest.TestCase):
    def test_list_members_from_zip(self):
        data = _results_zip(
            ("host-a-results.xml", "default"),
            ("nested/host-b-results.xml", "default"),
        )
        members = xccdf_results_zip.list_xccdf_results_files(
            data, source_prefix="bundle.zip"
        )
        self.assertEqual(len(members), 2)
        paths = sorted(path for path, _raw in members)
        self.assertIn("bundle.zip/host-a-results.xml", paths)
        self.assertIn("bundle.zip/nested/host-b-results.xml", paths)

    def test_skips_manual_xccdf_baseline(self):
        data = _results_zip(
            ("U_RHEL_8_V2R6_Manual-xccdf.xml", "baseline"),
            ("host-results.xml", "default"),
        )
        members = xccdf_results_zip.list_xccdf_results_files(data)
        self.assertEqual(len(members), 1)
        self.assertTrue(members[0][0].endswith("host-results.xml"))

    @patch.object(xccdf_results_zip, "MAX_RESULT_FILES", 1)
    def test_max_files_cap(self):
        data = _results_zip(
            ("a-results.xml", "default"),
            ("b-results.xml", "default"),
        )
        with self.assertRaises(ValueError):
            xccdf_results_zip.list_xccdf_results_files(data)

    @patch("importers.checklist_zip.MAX_MEMBER_BYTES", 80)
    def test_member_size_cap(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("big-results.xml", b"<TestResult><rule-result/></TestResult>" + b"x" * 200)
        with self.assertRaises(ValueError):
            xccdf_results_zip.list_xccdf_results_files(buf.getvalue())


class TestXccdfResultsArchiveService(unittest.TestCase):
    @patch.object(imports_svc, "import_checklist_batch")
    @patch("services.imports.list_xccdf_results_files")
    def test_import_xccdf_results_zip(self, mock_list, mock_batch):
        mock_list.return_value = [("scan/host-results.xml", b"<x/>")]
        mock_batch.return_value = {
            "stig_collection_id": "col1",
            "results": [{"status": "ok"}],
            "summary": {"total": 1, "succeeded": 1, "failed": 0, "created": 1, "updated": 0},
        }
        out = imports_svc.import_xccdf_results_zip(
            MagicMock(),
            _session(),
            "alice",
            "col1",
            b"PK",
            source_uri="scans.zip",
        )
        self.assertEqual(out["archive"]["results_members"], 1)
        entries = mock_batch.call_args[0][4]
        self.assertEqual(entries[0]["format"], "xccdf-results")

    @patch.object(imports_svc.grants_svc, "require_workspace_write")
    @patch.object(imports_svc, "import_checklist_file")
    def test_batch_mixed_success(self, mock_one, mock_write):
        mock_one.side_effect = [
            {
                "source_uri": "ok.xml",
                "format": "xccdf-results",
                "host": {"hostname": "h1", "created": True},
                "checklists": [{"_key": "c1", "created": True}],
                "stats": {"fail": 1},
                "finding_count": 3,
            },
            ValueError("baseline not found for stig Example_STIG"),
        ]
        out = imports_svc.import_checklist_batch(
            MagicMock(),
            _session(),
            "alice",
            "col1",
            [
                {"source_uri": "ok.xml", "format": "xccdf-results", "content": b"<x/>"},
                {"source_uri": "bad.xml", "format": "xccdf-results", "content": b"<y/>"},
            ],
        )
        self.assertEqual(out["summary"]["succeeded"], 1)
        self.assertEqual(out["summary"]["failed"], 1)
        mock_write.assert_called()


class TestXccdfResultsArchiveRest(unittest.TestCase):
    def _dispatch(
        self,
        method: str,
        rest_path: str,
        *,
        query: Dict[str, str] | None = None,
        session: Dict[str, Any] | None = None,
        raw_payload: str | None = None,
    ):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload: Dict[str, Any] = {
            "method": method,
            "session": session or _session(),
            "rest_path": rest_path,
            "query": query or {},
        }
        if raw_payload is not None:
            payload["payload"] = raw_payload
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.imports_svc, "import_xccdf_results_zip")
    def test_stig_imports_xccdf_results_zip(self, mock_zip):
        mock_zip.return_value = {
            "stig_collection_id": "col1",
            "results": [],
            "summary": {"total": 0, "succeeded": 0, "failed": 0, "created": 0, "updated": 0},
        }
        resp = self._dispatch(
            "POST",
            "stig_imports",
            raw_payload="PK\x03\x04fake",
            query={
                "format": "xccdf-results-zip",
                "stig_collection_id": "col1",
                "source_uri": "scans.zip",
            },
        )
        self.assertEqual(resp["status"], 200)
        mock_zip.assert_called_once()

    @patch.object(stig_rest_handler.imports_svc, "import_xccdf_results_zip")
    def test_acl_denied(self, mock_zip):
        mock_zip.side_effect = PermissionError("forbidden")
        resp = self._dispatch(
            "POST",
            "stig_imports",
            raw_payload="PK\x03\x04fake",
            query={
                "format": "xccdf-results-zip",
                "stig_collection_id": "col1",
            },
            session=_session(write=False),
        )
        self.assertEqual(resp["status"], 403)


if __name__ == "__main__":
    unittest.main()
