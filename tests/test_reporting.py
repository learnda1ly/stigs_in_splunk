"""Unit tests for collection metrics and findings aggregation."""

from __future__ import annotations

import os
import sys
import unittest

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


class TestFindingsFilters(unittest.TestCase):
    def test_parse_status_filter(self):
        parsed = reporting_svc._parse_status_filter("open,not_reviewed")
        self.assertEqual(parsed, {"open", "not_reviewed"})
        with self.assertRaises(ValueError):
            reporting_svc._parse_status_filter("bogus")


if __name__ == "__main__":
    unittest.main()
