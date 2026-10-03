"""Informational assessor status (not mapped to not_reviewed)."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from exporters import xccdf_results as xccdf_export  # noqa: E402
from importers import ingest as ingest_lib  # noqa: E402
from importers import xccdf_results as xccdf_results_import  # noqa: E402
from models import STATUS_TO_RESULT, normalize_status  # noqa: E402


class TestInformationalStatus(unittest.TestCase):
    def test_result_maps_to_informational_status(self):
        self.assertEqual(
            ingest_lib.status_from_result("informational"), "informational"
        )
        self.assertEqual(STATUS_TO_RESULT["informational"], "informational")

    def test_ckl_status_round_trip(self):
        self.assertEqual(
            normalize_status("Informational", source="ckl"), "informational"
        )

    def test_xccdf_results_import_keeps_informational(self):
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "minimal_xccdf_results.xml"
        )
        with open(fixture, "rb") as handle:
            content = handle.read()
        content = content.replace(
            b'result="fail"', b'result="informational"', 1
        )
        parsed = xccdf_results_import.parse_xccdf_results(content, source_uri="t.xml")
        review = parsed["checklists"][0]["reviews"][0]
        self.assertEqual(review["result"], "informational")
        seed = ingest_lib.review_seed_payload(review)
        self.assertEqual(seed["status"], "informational")

    def test_xccdf_export_informational_result(self):
        xml = xccdf_export.export_xccdf_results(
            {"_key": "cl1", "title": "host"},
            {"stig_id": "Example_STIG", "xccdf_benchmark_id": "xccdf_mil.disa.stig_benchmark_Example_STIG"},
            [
                {
                    "rule_id": "SV-000001",
                    "group_id": "V-000001",
                    "rule_id_src": "xccdf_mil.disa.stig_rule_SV-000001",
                }
            ],
            [
                {
                    "status": "informational",
                    "finding_details": "note",
                    "rule_id": "SV-000001",
                    "group_id": "V-000001",
                }
            ],
            {"hostname": "host01"},
        )
        self.assertIn('result="informational"', xml)


if __name__ == "__main__":
    unittest.main()
