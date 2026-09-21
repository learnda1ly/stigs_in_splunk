"""Unit tests for review submit / accept / reject workflow."""

import os
import sys
import unittest

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import access
import review_workflow
import validation


class ReviewWorkflowTransitionTests(unittest.TestCase):
    def _review(self, **kwargs):
        base = {
            "status": "open",
            "finding_details": "detail",
            "comments": "",
            "workflow_state": "draft",
        }
        base.update(kwargs)
        return base

    def test_submit_requires_complete(self):
        incomplete = self._review(finding_details="", comments="")
        with self.assertRaises(ValueError):
            review_workflow.transition("submit", incomplete)

    def test_submit_draft_to_submitted(self):
        rec = self._review()
        self.assertEqual(review_workflow.transition("submit", rec), "submitted")

    def test_cannot_accept_draft(self):
        with self.assertRaises(ValueError):
            review_workflow.transition("accept", self._review())

    def test_accept_submitted(self):
        rec = self._review(workflow_state="submitted")
        self.assertEqual(review_workflow.transition("accept", rec), "accepted")

    def test_reject_returns_draft(self):
        rec = self._review(workflow_state="submitted")
        self.assertEqual(review_workflow.transition("reject", rec), "draft")

    def test_annotate_includes_workflow(self):
        annotated = validation.annotate_review(self._review())
        self.assertEqual(annotated["workflow_state"], "draft")
        self.assertTrue(annotated["workflow_editable"])

    def test_open_unaccepted_metric(self):
        reviews = [
            {"status": "open", "workflow_state": "draft"},
            {"status": "open", "workflow_state": "accepted"},
            {"status": "not_a_finding", "workflow_state": "submitted"},
        ]
        counts = review_workflow.counts_for_metrics(reviews)
        self.assertEqual(counts["open_unaccepted"], 1)


class ReviewAcceptAccessTests(unittest.TestCase):
    def test_stig_review_accept_alone_does_not_accept(self):
        workspace = {"access_principals": "[]"}
        session = {
            "user": "assessor",
            "roles": ["stig_user"],
            "capabilities": {"stig_write": True, "stig_review_accept": True},
        }
        self.assertFalse(access.user_can_accept_reviews(workspace, session))

    def test_review_accept_principals(self):
        workspace = {
            "access_principals": "[]",
            "review_accept_principals": '["user:owner1"]',
        }
        session = {"user": "owner1", "roles": [], "capabilities": {}}
        self.assertTrue(access.user_can_accept_reviews(workspace, session))

    def test_owner_grant_can_accept(self):
        workspace = {"access_principals": "[]"}
        session = {"user": "alice", "roles": [], "capabilities": {}}
        grants = [
            {
                "principal": "user:alice",
                "grant_role": "owner",
                "acl_host_ids": "[]",
                "acl_baseline_ids": "[]",
            }
        ]
        self.assertTrue(access.user_can_accept_reviews(workspace, session, grants))


if __name__ == "__main__":
    unittest.main()
