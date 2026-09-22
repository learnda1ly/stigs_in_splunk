"""Light contract checks for Collection review governance UI wiring."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_REVIEW_APP = ROOT / "ui" / "src" / "pages" / "CollectionReviewApp.jsx"


class CollectionReviewGovernanceUiTest(unittest.TestCase):
    def test_collection_review_exposes_governance_batch_actions(self):
        src = COLLECTION_REVIEW_APP.read_text(encoding="utf-8")
        self.assertIn('apiPatch("stig_reviews/batch"', src)
        self.assertIn("onBatchWorkflow", src)
        for action in ("submit", "accept", "reject"):
            self.assertIn('onBatchWorkflow("' + action + '")', src)
        self.assertIn("WorkflowChip", src)
        self.assertIn("reviewIsEditable", src)
        self.assertRegex(
            src,
            re.compile(r"reject_feedback", re.MULTILINE),
        )


if __name__ == "__main__":
    unittest.main()
