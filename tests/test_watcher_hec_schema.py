"""Watcher-shaped HEC field aliases and schema normalization."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.events import build_finding_event, normalize_finding_event  # noqa: E402
from importers import ingest  # noqa: E402


class TestWatcherHecSchema(unittest.TestCase):
    def test_collection_id_aliases(self):
        event = normalize_finding_event(
            {
                "stig_collection_id": "coll-alias",
                "assetName": "h1",
                "benchmarkId": "Example_STIG",
                "ruleId": "SV-1",
                "result": "pass",
            }
        )
        self.assertEqual(event["collectionId"], "coll-alias")

    def test_source_ref_aliases(self):
        event = normalize_finding_event(
            {
                "assetName": "h1",
                "benchmarkId": "Example_STIG",
                "ruleId": "SV-1",
                "result": "pass",
                "source_uri": "scan/host.ckl",
            }
        )
        self.assertEqual(event["sourceRef"], "scan/host.ckl")

    def test_disa_id_prefix_stripping(self):
        event = normalize_finding_event(
            {
                "assetName": "h1",
                "benchmarkId": "xccdf_mil.disa.stig_benchmark_Example_STIG",
                "ruleId": "xccdf_mil.disa.stig_rule_SV-1_rule",
                "result": "fail",
                "stig": {"stig_id": "xccdf_mil.disa.stig_benchmark_Example_STIG"},
            }
        )
        self.assertEqual(event["benchmarkId"], "Example_STIG")
        self.assertEqual(event["ruleId"], "SV-1_rule")
        self.assertEqual(event["stig"]["stig_id"], "Example_STIG")

    def test_package_id_alias_on_event(self):
        event = normalize_finding_event(
            {
                "assetName": "h1",
                "benchmarkId": "STIG",
                "ruleId": "SV-1",
                "result": "pass",
                "packageId": "100002",
            }
        )
        self.assertEqual(event["package_id"], "100002")

    def test_build_finding_event_includes_package_id(self):
        review = ingest.streamed_review(
            rule_id="SV-1",
            group_id="V-1",
            result="pass",
            detail="ok",
            comment="",
        )
        review["packageId"] = "42"
        event = build_finding_event(
            review,
            stig={"stig_id": "Example_STIG"},
            target={"name": "host-a"},
            collection_id="c1",
        )
        self.assertEqual(event["package_id"], "42")


if __name__ == "__main__":
    unittest.main()
