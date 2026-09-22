"""STIG library browse: hierarchy grouping, revision metadata, rule detail REST."""

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

from services import baseline_library as lib  # noqa: E402
import stig_rest_handler  # noqa: E402


class TestBaselineLibraryGrouping(unittest.TestCase):
    def test_groups_by_stig_id_and_sorts_revisions(self):
        service = MagicMock()
        baselines = [
            {
                "_key": "b_old",
                "stig_id": "Example_STIG",
                "title": "Example",
                "version": "V1R1",
                "release_info": "Release: 1",
                "content_fingerprint": "fp1",
                "rule_count": 10,
                "imported_at": 100.0,
            },
            {
                "_key": "b_new",
                "stig_id": "Example_STIG",
                "title": "Example",
                "version": "V2R3",
                "release_info": "Release: 3",
                "content_fingerprint": "fp2",
                "rule_count": 12,
                "imported_at": 50.0,
            },
            {
                "_key": "other",
                "stig_id": "Other_STIG",
                "title": "Other",
                "version": "V1R1",
                "rule_count": 5,
                "imported_at": 10.0,
            },
        ]
        with patch.object(
            lib.baselines_svc, "list_baselines", return_value=baselines
        ):
            payload = lib.list_hierarchy(service)
        self.assertEqual(payload["benchmark_count"], 2)
        self.assertEqual(payload["baseline_count"], 3)
        example = next(
            b for b in payload["benchmarks"] if b["stig_id"] == "Example_STIG"
        )
        self.assertEqual(example["revision_count"], 2)
        self.assertEqual(example["latest_baseline_id"], "b_new")
        self.assertEqual(example["latest_version"], "V2R3")
        revs = example["revisions"]
        self.assertEqual(revs[0]["baseline_id"], "b_new")
        self.assertEqual(revs[0]["content_fingerprint"], "fp2")
        self.assertEqual(revs[1]["baseline_id"], "b_old")

    def test_get_benchmark_case_insensitive(self):
        service = MagicMock()
        with patch.object(
            lib.baselines_svc,
            "list_baselines",
            return_value=[
                {"_key": "x", "stig_id": "RHEL_8_STIG", "version": "V1R1"}
            ],
        ):
            row = lib.get_benchmark(service, "rhel_8_stig")
        self.assertIsNotNone(row)
        self.assertEqual(row["stig_id"], "RHEL_8_STIG")

    def test_rule_detail_by_kv_key(self):
        service = MagicMock()
        baseline = {"_key": "b1", "stig_id": "S", "title": "T", "version": "V1R1"}
        rule = {
            "_key": "rule_kv",
            "baseline_id": "b1",
            "rule_id": "SV-1",
            "group_id": "V-1",
        }
        with patch.object(lib.kv_client, "get_collection", return_value=MagicMock()), patch.object(
            lib.kv_client, "get_by_key", return_value=rule
        ), patch.object(lib.baselines_svc, "get_baseline", return_value=baseline):
            detail = lib.get_rule_by_key(service, "rule_kv")
        self.assertEqual(detail["baseline_id"], "b1")
        self.assertEqual(detail["rule"]["rule_id"], "SV-1")


class TestBaselineLibraryRest(unittest.TestCase):
    def _dispatch(self, method: str, rest_path: str, query=None):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": {
                "authtoken": "token",
                "user": "reader",
                "capabilities": {"stig_read": True},
            },
            "rest_path": rest_path,
            "query": query or [],
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.baseline_library_svc, "list_hierarchy")
    def test_get_hierarchy(self, mock_hierarchy):
        mock_hierarchy.return_value = {"benchmark_count": 1, "benchmarks": []}
        resp = self._dispatch("GET", "stig_baselines/hierarchy")
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertEqual(body["benchmark_count"], 1)

    @patch.object(stig_rest_handler.baseline_library_svc, "get_baseline_rule")
    def test_get_rule_in_baseline(self, mock_rule):
        mock_rule.return_value = {
            "baseline_id": "b1",
            "rule": {"_key": "rk", "rule_id": "SV-1"},
        }
        resp = self._dispatch(
            "GET",
            "stig_baselines/b1/rules/SV-1",
            [["group_id", "V-1"]],
        )
        self.assertEqual(resp["status"], 200)
        mock_rule.assert_called_once()
        self.assertEqual(mock_rule.call_args.kwargs.get("group_id"), "V-1")

    @patch.object(stig_rest_handler.baselines_svc, "get_baseline")
    def test_delete_baseline_still_requires_admin(self, mock_get):
        mock_get.return_value = {"_key": "b1"}
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "DELETE",
            "session": {
                "authtoken": "token",
                "user": "reader",
                "capabilities": {"stig_read": True, "stig_write": True},
            },
            "rest_path": "stig_baselines/b1",
            "query": [],
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)

    def test_unauthenticated_hierarchy_401(self):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": {},
            "rest_path": "stig_baselines/hierarchy",
            "query": [],
        }
        resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 401)


if __name__ == "__main__":
    unittest.main()
