"""REST handler tests for host STIG assign/unassign routes."""

from __future__ import annotations

import json
import os
import sys
import types
import unittest
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


class TestHostStigAssignRest(unittest.TestCase):
    def _session(self, *, write: bool = True):
        caps = {"stig_read": True}
        if write:
            caps["stig_write"] = True
        return {"authtoken": "token", "user": "writer", "capabilities": caps}

    def _dispatch(self, method: str, rest_path: str, body=None):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": self._session(),
            "rest_path": rest_path,
            "query": [],
        }
        if body is not None:
            payload["payload"] = json.dumps(body)
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.checklists_svc, "assign_stig_to_host")
    def test_post_stigs_created_201(self, mock_assign):
        mock_assign.return_value = ({"_key": "cl1", "baseline_id": "b1"}, True)
        resp = self._dispatch("POST", "stig_hosts/host1/stigs", {"baseline_id": "b1"})
        self.assertEqual(resp["status"], 201)
        body = json.loads(resp["payload"])
        self.assertTrue(body.get("created"))

    @patch.object(stig_rest_handler.checklists_svc, "assign_stig_to_host")
    def test_post_stigs_idempotent_200(self, mock_assign):
        mock_assign.return_value = ({"_key": "cl1", "baseline_id": "b1"}, False)
        resp = self._dispatch("POST", "stig_hosts/host1/stigs", {"stig_id": "Example_STIG"})
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertFalse(body.get("created"))

    @patch.object(stig_rest_handler.checklists_svc, "assign_stig_to_host")
    def test_post_stigs_acl_403(self, mock_assign):
        mock_assign.side_effect = PermissionError("write denied")
        resp = self._dispatch("POST", "stig_hosts/host1/stigs", {"baseline_id": "b1"})
        self.assertEqual(resp["status"], 403)

    @patch.object(stig_rest_handler.checklists_svc, "unassign_stig_from_host")
    def test_delete_stigs_success(self, mock_unassign):
        mock_unassign.return_value = {"deleted": "cl1", "baseline_id": "old_rev"}
        resp = self._dispatch("DELETE", "stig_hosts/host1/stigs/Example_STIG")
        self.assertEqual(resp["status"], 200)
        mock_unassign.assert_called_once()
        self.assertEqual(mock_unassign.call_args.args[2], "Example_STIG")

    @patch.object(stig_rest_handler.checklists_svc, "unassign_stig_from_host")
    def test_delete_stigs_without_write_403(self, mock_unassign):
        mock_unassign.side_effect = PermissionError("write denied")
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "DELETE",
            "session": self._session(write=False),
            "rest_path": "stig_hosts/host1/stigs/b1",
            "query": [],
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)
        mock_unassign.assert_called_once()


if __name__ == "__main__":
    unittest.main()
