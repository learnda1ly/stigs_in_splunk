"""Slim HEC finding events → KV seed / host metadata helpers."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.events import normalize_finding_event  # noqa: E402
from importers.ingest import review_seed_payload, reviews_to_seeds  # noqa: E402
from services.apply import _ingest_metadata_block, _merge_host_metadata  # noqa: E402


class TestSlimHecApply(unittest.TestCase):
    def test_normalize_slim_minimal(self):
        event = normalize_finding_event(
            {
                "collectionId": "coll-1",
                "assetName": "host01",
                "benchmarkId": "RHEL_8_STIG",
                "ruleId": "SV-12345r1_rule",
                "groupId": "V-12345",
                "result": "fail",
                "detail": "bad config",
                "comment": "fix me",
                "package_id": "100001",
                "source_product": "stigman-watcher",
                "sourceRef": "watcher://scan/1",
                "resultEngine": {"product": "Evaluate-STIG", "version": "1.0"},
            }
        )
        self.assertEqual(event["package_id"], "100001")
        self.assertEqual(event["collectionId"], "coll-1")

    def test_reviews_to_seeds_carries_package_id(self):
        event = normalize_finding_event(
            {
                "collectionId": "c",
                "assetName": "h",
                "benchmarkId": "STIG",
                "ruleId": "SV-1_rule",
                "groupId": "V-1",
                "result": "pass",
                "package_id": "42",
            }
        )
        seeds = reviews_to_seeds([event])
        self.assertIn("SV-1_rule", seeds)
        self.assertEqual(seeds["SV-1_rule"]["package_id"], "42")
        self.assertEqual(seeds["SV-1_rule"]["status"], "not_a_finding")

    def test_host_ingest_metadata_merge(self):
        event = normalize_finding_event(
            {
                "collectionId": "c",
                "assetName": "h",
                "benchmarkId": "STIG",
                "ruleId": "SV-1",
                "result": "pass",
                "source_product": "evaluate-stig",
                "collectionName": "Lab",
            }
        )
        block = _ingest_metadata_block(event)
        self.assertEqual(block["source_product"], "evaluate-stig")
        merged = _merge_host_metadata("{}", event, {})
        self.assertEqual(merged["ingest"]["source_product"], "evaluate-stig")
        self.assertEqual(merged["ingest"]["collectionName"], "Lab")

    def test_review_seed_payload_from_streamed(self):
        seed = review_seed_payload(
            {
                "result": "fail",
                "detail": "x",
                "comment": "y",
                "package_id": "9",
            }
        )
        self.assertEqual(seed["package_id"], "9")
        self.assertEqual(seed["status"], "open")


if __name__ == "__main__":
    unittest.main()
