"""Light contract checks for Collection review governance UI wiring."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_REVIEW_APP = ROOT / "ui" / "src" / "pages" / "CollectionReviewApp.jsx"
COLLECTION_REVIEW_BUNDLE = (
    ROOT / "package" / "appserver" / "static" / "ui" / "collection_review.js"
)
CACHE_BUSTER_LOADER = (
    ROOT / "package" / "appserver" / "static" / "stig_collection_review_ui.js"
)

JSX_GOVERNANCE_MARKERS = (
    'apiPatch("stig_reviews/batch"',
    "WorkflowChip",
    "reviewIsEditable",
    "reject_feedback",
)

BUNDLE_GOVERNANCE_MARKERS = (
    "stig_reviews/batch",
    "reject_feedback",
    "workflow_editable",
    "selected skipped",
)


def assert_markers(src, markers, label):
    for marker in markers:
        assert marker in src, f"{label} missing governance marker: {marker}"


class CollectionReviewGovernanceUiTest(unittest.TestCase):
    def test_collection_review_exposes_governance_batch_actions(self):
        src = COLLECTION_REVIEW_APP.read_text(encoding="utf-8")
        self.assertIn('apiPatch("stig_reviews/batch"', src)
        self.assertIn("onBatchWorkflow", src)
        for action in ("submit", "accept", "reject"):
            self.assertIn('onBatchWorkflow("' + action + '")', src)
        assert_markers(src, JSX_GOVERNANCE_MARKERS, "CollectionReviewApp.jsx")

    def test_built_collection_review_bundle_matches_governance_contract(self):
        bundle = COLLECTION_REVIEW_BUNDLE.read_text(encoding="utf-8")
        assert_markers(bundle, BUNDLE_GOVERNANCE_MARKERS, "collection_review.js")

    def test_collection_review_loader_cache_buster_monotonic(self):
        loader = CACHE_BUSTER_LOADER.read_text(encoding="utf-8")
        match = re.search(r"collection_review\.js\?b=(\d+)", loader)
        self.assertIsNotNone(match, "cache-buster query param missing")
        buster = int(match.group(1))
        self.assertGreaterEqual(buster, 1789440003)


if __name__ == "__main__":
    unittest.main()
