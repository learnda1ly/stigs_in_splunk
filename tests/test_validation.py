import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import validation  # noqa: E402


class TestFindingValidation(unittest.TestCase):
    def test_empty_details_and_comments_invalid(self):
        rec = validation.annotate_review(
            {"status": "open", "finding_details": "", "comments": "  "}
        )
        self.assertFalse(rec["valid"])
        self.assertEqual(rec["validation_errors"][0]["code"], "finding_text_required")

    def test_finding_details_alone_valid(self):
        rec = validation.annotate_review(
            {"finding_details": "Permission denied on /etc/shadow", "comments": ""}
        )
        self.assertTrue(rec["valid"])
        self.assertEqual(rec["validation_errors"], [])

    def test_comments_alone_valid(self):
        rec = validation.annotate_review(
            {"finding_details": "", "comments": "Accepted risk; see POA&M."}
        )
        self.assertTrue(rec["valid"])

    def test_completed_matches_valid(self):
        empty = {"finding_details": "", "comments": ""}
        filled = {"finding_details": "ok", "comments": ""}
        self.assertFalse(validation.is_completed(empty))
        self.assertTrue(validation.is_completed(filled))

    def test_whitespace_only_is_empty(self):
        self.assertFalse(
            validation.is_valid({"finding_details": "\n\t", "comments": "   "})
        )


if __name__ == "__main__":
    unittest.main()
