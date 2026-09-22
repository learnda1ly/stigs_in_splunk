"""Async collection archive export jobs."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
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
from services import collection_jobs as jobs  # noqa: E402


def _session(user: str = "alice") -> Dict[str, Any]:
    return {
        "authtoken": "token",
        "user": user,
        "roles": [],
        "capabilities": {"stig_read": True, "stig_write": True},
    }


class TestCollectionJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stig_coll_jobs_")
        self.env_patch = patch.dict(os.environ, {"STIG_COLLECTION_JOBS_SYNC": "1"})
        self.env_patch.start()
        self.root_patch = patch.object(jobs, "_jobs_root", return_value=self.tmp)
        self.root_patch.start()
        self.service = MagicMock()
        self.session = _session()
        self.ws = {
            "_key": "ws1",
            "name": "Lab",
            "access_principals": '["user:alice"]',
        }

    def tearDown(self):
        self.root_patch.stop()
        self.env_patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("services.collection_jobs.checklists_svc.export_collection_archive")
    @patch("services.collection_jobs.checklists_svc._require_workspace_export_access")
    def test_create_poll_download_succeeds(self, mock_acl, mock_export):
        mock_acl.return_value = self.ws
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w") as archive:
            archive.writestr("host_stig.cklb", "{}")
        mock_export.return_value = {
            "filename": "stig-archive-Lab-cklb.zip",
            "format": "cklb",
            "count": 1,
            "files": ["host_stig.cklb"],
            "content_base64": base64.b64encode(zip_bytes.getvalue()).decode("ascii"),
        }

        created = jobs.create_archive_export_job(
            self.service, "ws1", self.session, "alice", "cklb"
        )
        self.assertEqual(created["status"], "succeeded")
        self.assertEqual(created["operation"], "archive_export")
        job_id = created["job_id"]
        self.assertIn("download_path", created["result"])

        polled = jobs.get_job(job_id, "ws1", "alice")
        self.assertEqual(polled["status"], "succeeded")

        payload = jobs.download_job_result(job_id, "ws1", "alice")
        self.assertEqual(payload["format"], "cklb")
        self.assertEqual(payload["count"], 1)
        raw = base64.b64decode(payload["content_base64"])
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            self.assertEqual(archive.namelist(), ["host_stig.cklb"])

    @patch("services.collection_jobs.checklists_svc.export_collection_archive")
    @patch("services.collection_jobs.checklists_svc._require_workspace_export_access")
    def test_other_user_denied(self, mock_acl, mock_export):
        mock_acl.return_value = self.ws
        mock_export.return_value = {
            "filename": "x.zip",
            "format": "ckl",
            "count": 0,
            "files": [],
            "content_base64": base64.b64encode(b"PK").decode("ascii"),
        }
        created = jobs.create_archive_export_job(
            self.service, "ws1", self.session, "alice", "ckl"
        )
        with self.assertRaises(PermissionError):
            jobs.get_job(created["job_id"], "ws1", "bob")

    @patch("services.collection_jobs.checklists_svc.export_collection_archive")
    @patch("services.collection_jobs.checklists_svc._require_workspace_export_access")
    def test_export_failure_marks_job_failed(self, mock_acl, mock_export):
        mock_acl.return_value = self.ws
        mock_export.side_effect = ValueError("no checklists match export filter")
        created = jobs.create_archive_export_job(
            self.service, "ws1", self.session, "alice", "cklb"
        )
        self.assertEqual(created["status"], "failed")
        self.assertIn("no checklists", (created.get("error") or "").lower())
        with self.assertRaises(ValueError):
            jobs.download_job_result(created["job_id"], "ws1", "alice")


class TestCollectionJobsRest(unittest.TestCase):
    @patch.object(stig_rest_handler.collection_jobs_svc, "create_archive_export_job")
    def test_rest_create_job(self, mock_create):
        mock_create.return_value = {
            "job_id": "abc",
            "status": "pending",
            "operation": "archive_export",
            "result": None,
        }
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": _session(),
            "rest_path": "stig_collections/ws1/jobs",
            "payload": json.dumps({"format": "cklb"}),
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 201)
        mock_create.assert_called_once()

    @patch.object(stig_rest_handler.collection_jobs_svc, "get_job")
    def test_rest_get_job_acl_403(self, mock_get):
        mock_get.side_effect = PermissionError("access denied to collection job")
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": _session("bob"),
            "rest_path": "stig_collections/ws1/jobs/abc",
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)


if __name__ == "__main__":
    unittest.main()
