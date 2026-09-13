import copy
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers import xccdf  # noqa: E402
from models import baseline_content_fingerprint  # noqa: E402


class TestBaselineFingerprint(unittest.TestCase):
    def setUp(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")
        with open(fixture, "rb") as handle:
            self.meta, self.rules = xccdf.parse_xccdf(handle.read())

    def test_stable_for_same_content(self):
        a = baseline_content_fingerprint(self.meta, self.rules)
        b = baseline_content_fingerprint(self.meta, self.rules)
        self.assertEqual(a, b)

    def test_changes_when_version_changes(self):
        meta_v2 = copy.deepcopy(self.meta)
        meta_v2["version"] = "V9R9"
        self.assertNotEqual(
            baseline_content_fingerprint(self.meta, self.rules),
            baseline_content_fingerprint(meta_v2, self.rules),
        )

    def test_changes_when_rule_content_changes(self):
        rules2 = copy.deepcopy(self.rules)
        rules2[0]["check_content"] = rules2[0]["check_content"] + " extra"
        from models import check_content_hash

        rules2[0]["check_content_hash"] = check_content_hash(rules2[0]["check_content"])
        self.assertNotEqual(
            baseline_content_fingerprint(self.meta, self.rules),
            baseline_content_fingerprint(self.meta, rules2),
        )


if __name__ == "__main__":
    unittest.main()
