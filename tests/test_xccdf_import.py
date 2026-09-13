import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers import xccdf  # noqa: E402


class TestXccdfImport(unittest.TestCase):
    def test_parse_minimal_benchmark(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")
        with open(fixture, "rb") as handle:
            content = handle.read()
        meta, rules = xccdf.parse_xccdf(content, source_uri="minimal_benchmark.xml")
        self.assertEqual(meta["source_type"], "xccdf")
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule["group_id"], "V-000001")
        self.assertEqual(rule["rule_id"], "SV-000001")
        self.assertEqual(rule["severity"], "high")
        self.assertTrue(rule["check_content_hash"])


if __name__ == "__main__":
    unittest.main()
