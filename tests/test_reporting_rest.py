"""REST handler tests for POA&M and findings aggregate routes."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import types

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


class TestReportingRestRoutes(unittest.TestCase):
    def _session(self):
        return {
            "authtoken": "token",
            "user": "alice",
            "capabilities": {"stig_read": True},
        }

    def _dispatch(self, rest_path: str, query=None):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": self._session(),
            "rest_path": rest_path,
            "query": query or {},
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.reporting_svc, "collection_poam")
    def test_poam_csv_response_shape(self, mock_poam):
        mock_poam.return_value = {
            "format": "csv",
            "filename": "stig_poam_ws1.csv",
            "content": "POAM ID,Weakness ID\n1,V-1\n",
            "row_count": 1,
            "filters": {"status": ["open"]},
        }
        resp = self._dispatch("/stig_collections/ws1/poam", {"format": "csv"})
        self.assertEqual(resp["status"], 200)
        self.assertIn("POAM ID", resp["payload"])
        headers = dict(resp.get("headers") or [])
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertIn("stig_poam_ws1.csv", headers.get("Content-Disposition", ""))

    @patch.object(stig_rest_handler.reporting_svc, "collection_poam")
    def test_poam_xlsx_json_response(self, mock_poam):
        mock_poam.return_value = {
            "format": "xlsx",
            "filename": "stig_poam_ws1.xlsx",
            "content_base64": "UEsDBAoAAAAAAA==",
            "row_count": 0,
        }
        resp = self._dispatch("/stig_collections/ws1/poam", {"format": "xlsx"})
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertEqual(body["format"], "xlsx")
        self.assertIn("content_base64", body)

    @patch.object(stig_rest_handler.reporting_svc, "collection_findings_aggregate")
    def test_aggregate_not_found_when_acl_denies(self, mock_agg):
        mock_agg.side_effect = KeyError("secret")
        resp = self._dispatch(
            "/stig_collections/secret/findings/aggregate",
            {"group_by": "rule_id"},
        )
        self.assertEqual(resp["status"], 404)

    @patch.object(stig_rest_handler.reporting_svc, "collection_unreviewed_rules")
    def test_unreviewed_rules_route(self, mock_rules):
        mock_rules.return_value = {"total_unreviewed": 0, "rules": []}
        resp = self._dispatch("/stig_collections/ws1/unreviewed/rules")
        self.assertEqual(resp["status"], 200)
        mock_rules.assert_called_once()

    @patch.object(stig_rest_handler.reporting_svc, "collection_unreviewed_assets")
    def test_unreviewed_assets_not_found_when_acl_denies(self, mock_assets):
        mock_assets.side_effect = KeyError("secret")
        resp = self._dispatch("/stig_collections/secret/unreviewed/assets")
        self.assertEqual(resp["status"], 404)

    @patch.object(stig_rest_handler.reporting_svc, "meta_collection_metrics")
    def test_meta_metrics_route(self, mock_meta):
        mock_meta.return_value = {"workspace_count": 0, "workspaces": [], "summary": {}}
        resp = self._dispatch("/stig_collections/meta/metrics")
        self.assertEqual(resp["status"], 200)
        mock_meta.assert_called_once()

    @patch.object(stig_rest_handler.reporting_svc, "meta_collection_metrics_summary")
    def test_meta_metrics_summary_route(self, mock_summary):
        mock_summary.return_value = {"workspace_count": 1, "summary": {}}
        resp = self._dispatch("/stig_collections/meta/metrics/summary")
        self.assertEqual(resp["status"], 200)
        mock_summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
