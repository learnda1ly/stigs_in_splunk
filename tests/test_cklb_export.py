import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from exporters import cklb  # noqa: E402
from importers import xccdf  # noqa: E402


class TestCklbExport(unittest.TestCase):
    def test_export_shape(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")
        with open(fixture, "rb") as handle:
            meta, rules = xccdf.parse_xccdf(handle.read())
        baseline = {"_key": "baseline-1", **meta}
        checklist = {
            "_key": "checklist-1",
            "title": "Test",
            "mode": 1,
            "target_data": json.dumps({"host_name": "h1"}),
        }
        host = {"hostname": "h1", "ip_address": "10.0.0.2"}
        reviews = {
            "V-000001": {
                "status": "open",
                "finding_details": "bad",
                "comments": "",
                "package_id": "PKG-42",
            }
        }
        out = cklb.export_cklb(checklist, baseline, rules, reviews, host)
        doc = json.loads(out)
        self.assertEqual(doc["mode"], 2)
        self.assertTrue(doc["active"])
        rule = doc["stigs"][0]["rules"][0]
        self.assertEqual(rule["status"], "open")
        self.assertEqual(rule["package_id"], "PKG-42")
        self.assertIn("group_tree", rule)
        self.assertIn("srg_id", rule)
        self.assertEqual(list(doc["target_data"].keys())[0], "target_type")


if __name__ == "__main__":
    unittest.main()
