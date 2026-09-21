import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers import ingest, xccdf_results  # noqa: E402


class TestXccdfResultsImport(unittest.TestCase):
    def test_parse_minimal_results(self):
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "minimal_xccdf_results.xml"
        )
        with open(fixture, "rb") as handle:
            content = handle.read()
        parsed = xccdf_results.parse_xccdf_results(content, source_uri="minimal_xccdf_results.xml")
        self.assertEqual(parsed["target"]["name"], "scan-host-01")
        self.assertEqual(len(parsed["checklists"]), 1)
        checklist = parsed["checklists"][0]
        self.assertEqual(checklist["benchmarkId"], "Example_STIG")
        self.assertEqual(checklist["stats"]["fail"], 1)
        self.assertEqual(checklist["stats"]["pass"], 1)
        self.assertEqual(checklist["stats"]["notapplicable"], 1)
        review = checklist["reviews"][0]
        self.assertEqual(review["result"], "fail")
        self.assertEqual(review["ruleId"], "SV-000001")
        self.assertEqual(review["groupId"], "V-000001")

    def test_detect_format(self):
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "minimal_xccdf_results.xml"
        )
        with open(fixture, "rb") as handle:
            content = handle.read()
        self.assertEqual(
            ingest.detect_format("host-results.xml", content), "xccdf-results"
        )
        parsed = ingest.parse_ingest("xccdf-results", content, source_uri="host-results.xml")
        self.assertEqual(parsed["target"]["name"], "scan-host-01")


if __name__ == "__main__":
    unittest.main()
