"""Unit tests for collection metrics and findings aggregation."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import reporting as reporting_svc  # noqa: E402


class TestAggregateMetrics(unittest.TestCase):
    def test_counts_status_and_severity(self):
        reviews = [
            {
                "status": "not_reviewed",
                "baseline_id": "b1",
                "rule_id": "r1",
                "group_id": "V-1",
            },
            {
                "status": "open",
                "baseline_id": "b1",
                "rule_id": "r2",
                "group_id": "V-2",
                "finding_details": "issue",
            },
            {
                "status": "open",
                "baseline_id": "b1",
                "rule_id": "r3",
                "group_id": "V-3",
                "comments": "note",
            },
            {
                "status": "not_a_finding",
                "baseline_id": "b1",
                "rule_id": "r4",
                "group_id": "V-4",
                "finding_details": "ok",
            },
        ]
        severity_index = {
            ("b1", "r1", "V-1"): "medium",
            ("b1", "r2", "V-2"): "high",
            ("b1", "r3", "V-3"): "low",
            ("b1", "r4", "V-4"): "medium",
        }
        metrics = reporting_svc.aggregate_metrics(
            reviews,
            severity_index,
            host_count=2,
            checklist_count=3,
        )
        self.assertEqual(metrics["totals"]["reviews"], 4)
        self.assertEqual(metrics["totals"]["hosts"], 2)
        self.assertEqual(metrics["by_status"]["open"], 2)
        self.assertEqual(metrics["by_status"]["not_reviewed"], 1)
        self.assertEqual(metrics["completion"]["open_findings"], 2)
        self.assertEqual(metrics["completion"]["open_findings_by_status"], 2)
        self.assertEqual(metrics["completion"]["valid"], 3)
        self.assertEqual(metrics["completion"]["percent_reviewed"], 75.0)
        self.assertEqual(metrics["by_severity"]["high"], 1)
        self.assertEqual(metrics["open_by_severity"]["high"], 1)
        self.assertEqual(metrics["open_by_severity"]["low"], 1)

    def test_open_findings_exclude_accepted_workflow(self):
        reviews = [
            {
                "status": "open",
                "workflow_state": "accepted",
                "baseline_id": "b1",
                "rule_id": "r1",
                "group_id": "V-1",
            },
            {
                "status": "open",
                "workflow_state": "submitted",
                "baseline_id": "b1",
                "rule_id": "r2",
                "group_id": "V-2",
            },
        ]
        severity_index = {
            ("b1", "r1", "V-1"): "high",
            ("b1", "r2", "V-2"): "low",
        }
        metrics = reporting_svc.aggregate_metrics(
            reviews, severity_index, host_count=1, checklist_count=1
        )
        self.assertEqual(metrics["completion"]["open_findings"], 1)
        self.assertEqual(metrics["completion"]["open_findings_by_status"], 2)
        self.assertEqual(metrics["open_by_severity"].get("low"), 1)
        self.assertNotIn("high", metrics["open_by_severity"])

    def test_review_severity_unknown_without_rule(self):
        review = {"baseline_id": "b1", "rule_id": "missing", "group_id": "V-9"}
        self.assertEqual(
            reporting_svc.review_severity(review, {}),
            "unknown",
        )


class TestRollupAggregateMetrics(unittest.TestCase):
    def test_sums_totals_and_completion_percent(self):
        parts = [
            {
                "totals": {"hosts": 1, "checklists": 2, "reviews": 4},
                "completion": {
                    "reviewed": 3,
                    "not_reviewed": 1,
                    "valid": 2,
                    "open_findings": 1,
                    "open_findings_by_status": 2,
                },
                "workflow": {"draft": 1, "submitted": 0, "accepted": 0, "rejected": 0, "open_unaccepted": 1},
                "by_status": {"open": 2, "not_reviewed": 1, "not_a_finding": 1, "not_applicable": 0},
                "by_severity": {"high": 1, "low": 1},
                "open_by_severity": {"high": 1},
            },
            {
                "totals": {"hosts": 2, "checklists": 1, "reviews": 6},
                "completion": {
                    "reviewed": 6,
                    "not_reviewed": 0,
                    "valid": 5,
                    "open_findings": 0,
                    "open_findings_by_status": 1,
                },
                "workflow": {"draft": 0, "submitted": 1, "accepted": 1, "rejected": 0, "open_unaccepted": 0},
                "by_status": {"open": 1, "not_reviewed": 0, "not_a_finding": 5, "not_applicable": 0},
                "by_severity": {"medium": 3},
                "open_by_severity": {},
            },
        ]
        rolled = reporting_svc.rollup_aggregate_metrics(parts)
        self.assertEqual(rolled["totals"]["hosts"], 3)
        self.assertEqual(rolled["totals"]["reviews"], 10)
        self.assertEqual(rolled["completion"]["reviewed"], 9)
        self.assertEqual(rolled["completion"]["percent_reviewed"], 90.0)
        self.assertEqual(rolled["by_severity"]["high"], 1)
        self.assertEqual(rolled["by_severity"]["medium"], 3)


class TestFindingsFilters(unittest.TestCase):
    def test_parse_status_filter(self):
        parsed = reporting_svc._parse_status_filter("open,not_reviewed")
        self.assertEqual(parsed, {"open", "not_reviewed"})
        with self.assertRaises(ValueError):
            reporting_svc._parse_status_filter("bogus")

    def test_parse_group_by(self):
        self.assertEqual(
            reporting_svc._parse_group_by("group_id,cci"),
            {"group_id", "cci"},
        )
        with self.assertRaises(ValueError):
            reporting_svc._parse_group_by("hostname")


class TestFindingsAggregate(unittest.TestCase):
    @patch.object(reporting_svc, "_list_collection_findings")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_aggregate_open_by_rule_and_cci(self, mock_require, mock_list):
        mock_require.return_value = {"name": "Lab"}
        mock_list.return_value = (
            [
                {
                    "hostname": "h1",
                    "group_id": "V-1",
                    "rule_id": "r1",
                    "severity": "high",
                    "baseline_id": "b1",
                    "stig_id": "STIG_A",
                },
                {
                    "hostname": "h2",
                    "group_id": "V-1",
                    "rule_id": "r1",
                    "severity": "high",
                    "baseline_id": "b1",
                    "stig_id": "STIG_A",
                },
            ],
            {"status": ["open"]},
            {
                "rule_meta_index": {
                    ("b1", "r1", "V-1"): {"ccis": ["CCI-000366"]},
                }
            },
        )
        service = MagicMock()
        session = {"user": "u", "capabilities": {"stig_read": True}}
        out = reporting_svc.collection_findings_aggregate(
            service, "ws1", session, {"group_by": "rule_id,cci"}
        )
        self.assertEqual(out["open_findings_total"], 2)
        self.assertEqual(out["by_rule_id"][0]["rule_id"], "r1")
        self.assertEqual(out["by_rule_id"][0]["count"], 2)
        self.assertEqual(out["by_cci"][0]["cci"], "CCI-000366")
        self.assertEqual(out["by_cci"][0]["count"], 2)
        self.assertEqual(out["by_cci"][0]["host_count"], 2)

    @patch.object(reporting_svc, "_list_collection_findings")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_aggregate_rule_id_scoped_by_baseline(self, mock_require, mock_list):
        mock_require.return_value = {"name": "Lab"}
        mock_list.return_value = (
            [
                {
                    "hostname": "h1",
                    "group_id": "V-1",
                    "rule_id": "shared_rule",
                    "severity": "high",
                    "baseline_id": "b1",
                    "stig_id": "STIG_A",
                },
                {
                    "hostname": "h2",
                    "group_id": "V-2",
                    "rule_id": "shared_rule",
                    "severity": "low",
                    "baseline_id": "b2",
                    "stig_id": "STIG_B",
                },
            ],
            {"status": ["open"]},
            {"rule_meta_index": {}},
        )
        out = reporting_svc.collection_findings_aggregate(
            MagicMock(),
            "ws1",
            {"user": "u"},
            {"group_by": "rule_id"},
        )
        self.assertEqual(len(out["by_rule_id"]), 2)
        stigs = sorted(row["stig_id"] for row in out["by_rule_id"])
        self.assertEqual(stigs, ["STIG_A", "STIG_B"])
        self.assertTrue(all(row["count"] == 1 for row in out["by_rule_id"]))

    @patch.object(reporting_svc.grants_svc, "query_grants")
    @patch.object(reporting_svc.collections_svc, "get_collection")
    @patch.object(reporting_svc.access, "user_can_read_collection")
    def test_aggregate_hidden_workspace_raises_key_error(
        self, mock_can_read, mock_get, mock_grants
    ):
        mock_get.return_value = {"_key": "secret", "access_principals": "[]"}
        mock_grants.return_value = []
        mock_can_read.return_value = False
        with self.assertRaises(KeyError):
            reporting_svc.collection_findings_aggregate(
                MagicMock(), "secret", {"user": "bob", "capabilities": {"stig_read": True}}, {}
            )


class TestCollectionPoam(unittest.TestCase):
    @patch.object(reporting_svc, "_list_collection_findings")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_poam_json_rows(self, mock_require, mock_list):
        mock_require.return_value = {"name": "Prod"}
        mock_list.return_value = (
            [
                {
                    "hostname": "app01",
                    "group_id": "V-9",
                    "rule_id": "r9",
                    "severity": "low",
                    "stig_id": "STIG",
                    "baseline_id": "b1",
                    "status": "open",
                }
            ],
            {"status": ["open"]},
            {
                "rule_meta_index": {
                    ("b1", "r9", "V-9"): {
                        "rule_title": "Title",
                        "ccis": ["CCI-1"],
                    }
                }
            },
        )
        out = reporting_svc.collection_poam(
            MagicMock(), "ws9", {"user": "u"}, {"format": "json"}
        )
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["weakness_id"], "V-9")
        alt = out["splunk_alternative"]
        self.assertIn("governance_filter", alt)
        self.assertIn("note", alt)

    @patch.object(reporting_svc.grants_svc, "query_grants")
    @patch.object(reporting_svc.collections_svc, "get_collection")
    @patch.object(reporting_svc.access, "user_can_read_collection")
    def test_poam_hidden_workspace_raises_key_error(
        self, mock_can_read, mock_get, mock_grants
    ):
        mock_get.return_value = {"_key": "secret"}
        mock_grants.return_value = []
        mock_can_read.return_value = False
        with self.assertRaises(KeyError):
            reporting_svc.collection_poam(
                MagicMock(), "secret", {"user": "bob", "capabilities": {"stig_read": True}}, {}
            )


if __name__ == "__main__":
    unittest.main()
