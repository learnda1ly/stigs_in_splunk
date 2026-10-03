"""STIG Manager–style metrics export groupings and review ages."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import reporting as reporting_svc  # noqa: E402


class TestMetricsExport(unittest.TestCase):
    def test_review_age_bounds(self):
        ages = reporting_svc._metrics_export_review_ages(
            [{"updated_at": 100.0}, {"updated_at": 200.0}]
        )
        self.assertEqual(ages["oldest_review_at"], 100.0)
        self.assertEqual(ages["newest_review_at"], 200.0)
        self.assertGreater(ages["oldest_review_age_seconds"], ages["newest_review_age_seconds"])

    def test_result_counts_include_informational(self):
        counts = reporting_svc._metrics_export_result_counts(
            [{"status": "informational"}, {"status": "open"}]
        )
        self.assertEqual(counts["informational"], 1)
        self.assertEqual(counts["fail"], 1)

    @patch.object(reporting_svc, "_collect_collection_reviews")
    @patch.object(reporting_svc, "_require_read_collection")
    @patch.object(reporting_svc.settings_svc, "get_settings")
    @patch.object(reporting_svc.settings_svc, "is_governance_enabled", return_value=True)
    def test_collection_grouping_single_row(
        self, _gov, _settings, mock_require, mock_collect
    ):
        mock_require.return_value = {"name": "Lab"}
        reviews = [
            {
                "status": "open",
                "updated_at": 50.0,
                "workflow_state": "draft",
                "_checklist": {"_key": "c1"},
                "_host": {"_key": "h1", "hostname": "a"},
                "_baseline": {"_key": "b1", "stig_id": "STIG"},
            }
        ]
        mock_collect.return_value = (reviews, {})
        payload = reporting_svc.collection_metrics_export(
            MagicMock(),
            "coll1",
            {"user": "admin"},
            {"grouping": "collection"},
        )
        self.assertEqual(payload["row_count"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["review_count"], 1)
        self.assertEqual(row["results"]["fail"], 1)
        self.assertIsNotNone(row["oldest_review_at"])

    @patch.object(reporting_svc, "_require_read_collection")
    def test_invalid_grouping_raises(self, mock_require):
        mock_require.return_value = {"name": "Lab"}
        with self.assertRaises(ValueError):
            reporting_svc.collection_metrics_export(
                MagicMock(),
                "coll1",
                {"user": "admin"},
                {"grouping": "hostname"},
            )


if __name__ == "__main__":
    unittest.main()
