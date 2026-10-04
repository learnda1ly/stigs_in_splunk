"""Catalog latest revision resolution (VxRy, exclude draft)."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import baselines as baselines_svc  # noqa: E402


class TestFindBaselineByStig(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()

    @patch.object(baselines_svc, "list_baselines")
    def test_latest_picks_highest_revision_not_import_time(self, mock_list):
        mock_list.return_value = [
            {
                "_key": "old_import",
                "stig_id": "Example_STIG",
                "version": "V1R1",
                "benchmark_status": "accepted",
                "imported_at": 999.0,
                "stig_collection_id": "",
            },
            {
                "_key": "newer_rev",
                "stig_id": "Example_STIG",
                "version": "V2R3",
                "benchmark_status": "accepted",
                "imported_at": 1.0,
                "stig_collection_id": "",
            },
        ]
        found = baselines_svc.find_baseline_by_stig(self.service, "Example_STIG")
        self.assertEqual(found["_key"], "newer_rev")

    @patch.object(baselines_svc, "list_baselines")
    def test_latest_skips_draft_revision(self, mock_list):
        mock_list.return_value = [
            {
                "_key": "draft_rev",
                "stig_id": "Example_STIG",
                "version": "V9R9",
                "benchmark_status": "draft",
                "imported_at": 500.0,
                "stig_collection_id": "",
            },
            {
                "_key": "accepted_rev",
                "stig_id": "Example_STIG",
                "version": "V2R1",
                "benchmark_status": "accepted",
                "imported_at": 1.0,
                "stig_collection_id": "",
            },
        ]
        found = baselines_svc.find_baseline_by_stig(self.service, "Example_STIG")
        self.assertEqual(found["_key"], "accepted_rev")

    @patch.object(baselines_svc, "list_baselines")
    def test_explicit_version_may_match_draft(self, mock_list):
        mock_list.return_value = [
            {
                "_key": "draft_rev",
                "stig_id": "Example_STIG",
                "version": "V9R9",
                "benchmark_status": "draft",
                "imported_at": 500.0,
                "stig_collection_id": "",
            },
        ]
        found = baselines_svc.find_baseline_by_stig(
            self.service, "Example_STIG", "V9R9"
        )
        self.assertEqual(found["_key"], "draft_rev")

    @patch.object(baselines_svc, "list_baselines")
    def test_latest_returns_none_when_only_drafts(self, mock_list):
        mock_list.return_value = [
            {
                "_key": "draft_only",
                "stig_id": "Example_STIG",
                "version": "V9R9",
                "benchmark_status": "draft",
                "imported_at": 500.0,
                "stig_collection_id": "",
            },
        ]
        found = baselines_svc.find_baseline_by_stig(self.service, "Example_STIG")
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
