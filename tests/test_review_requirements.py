"""Tests for per-workspace review validation policy."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import validation  # noqa: E402
from services import review_requirements as req_svc  # noqa: E402
from services import reviews as reviews_svc  # noqa: E402


class ReviewRequirementsPolicyTests(unittest.TestCase):
    def test_defaults_match_legacy_or_rule(self):
        policy = req_svc.default_policy()
        self.assertFalse(validation.is_valid({"finding_details": "", "comments": ""}, policy))
        self.assertTrue(
            validation.is_valid({"finding_details": "x", "comments": ""}, policy)
        )

    def test_empty_collection_field_uses_defaults(self):
        policy = req_svc.parse_policy_from_collection({})
        self.assertEqual(policy, req_svc.default_policy())

    def test_require_both_fields(self):
        policy = req_svc.normalize_policy(
            {
                "require_finding_details": True,
                "require_comments": True,
                "min_finding_details_length": 3,
                "min_comments_length": 5,
            }
        )
        review = {
            "status": "open",
            "finding_details": "ab",
            "comments": "tiny",
        }
        issues = validation.collect_issues(review, policy)
        codes = {i["code"] for i in issues}
        self.assertIn("finding_details_too_short", codes)
        self.assertIn("comments_too_short", codes)

    def test_status_scope_skips_validation(self):
        policy = req_svc.normalize_policy(
            {
                "require_finding_details": True,
                "applies_to_statuses": ["open"],
            }
        )
        review = {"status": "not_reviewed", "finding_details": "", "comments": ""}
        self.assertTrue(validation.is_valid(review, policy))

    def test_invalid_status_in_scope_raises(self):
        with self.assertRaises(ValueError):
            req_svc.normalize_policy({"applies_to_statuses": ["bogus"]})

    def test_min_length_implies_require_flag(self):
        policy = req_svc.normalize_policy({"min_comments_length": 10})
        self.assertTrue(policy["require_comments"])
        self.assertFalse(
            validation.is_valid(
                {"status": "open", "finding_details": "long enough", "comments": ""},
                policy,
            )
        )


class ReviewRequirementsRestTests(unittest.TestCase):
    @patch("services.grants.workspace_context")
    @patch.object(req_svc, "collections_svc")
    def test_get_requires_read(self, mock_collections, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True),
            [],
        )
        mock_collections.get_collection.return_value = {"_key": "ws1"}
        body = req_svc.get_requirements(MagicMock(), "ws1", {"user": "u"})
        self.assertEqual(body["stig_collection_id"], "ws1")
        self.assertIn("review_requirements", body)

    @patch("services.grants.workspace_context")
    def test_get_denied_without_read(self, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=False),
            [],
        )
        with self.assertRaises(KeyError):
            req_svc.get_requirements(MagicMock(), "ws1", {"user": "u"})

    @patch("services.grants.workspace_context")
    def test_patch_requires_write(self, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=False),
            [],
        )
        with self.assertRaises(PermissionError):
            req_svc.patch_requirements(
                MagicMock(),
                "ws1",
                {"review_requirements": {"require_comments": True}},
                "u",
                {"user": "u"},
            )

    @patch("services.grants.workspace_context")
    @patch.object(req_svc, "kv_client")
    @patch.object(req_svc, "collections_svc")
    def test_patch_persists_json(self, mock_collections, mock_kv, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = {"_key": "ws1"}
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.update_record.return_value = {"_key": "ws1"}
        mock_kv.kv_record.side_effect = lambda r: r

        with patch.object(req_svc, "audit") as mock_audit:
            mock_audit.log_event = MagicMock()
            out = req_svc.patch_requirements(
                MagicMock(),
                "ws1",
                {"require_comments": True, "min_comments_length": 10},
                "owner",
                {"user": "owner"},
            )
        self.assertTrue(out["review_requirements"]["require_comments"])
        self.assertEqual(out["review_requirements"]["min_comments_length"], 10)


class ReviewPatchEnforcementTests(unittest.TestCase):
    @patch.object(reviews_svc, "review_requirements_svc")
    @patch.object(reviews_svc, "kv_client")
    @patch.object(reviews_svc, "grants_svc")
    @patch.object(reviews_svc, "checklists_svc")
    def test_patch_rejects_invalid_content(
        self, mock_checklists, mock_grants, mock_kv, mock_req
    ):
        mock_req.get_policy.return_value = req_svc.normalize_policy(
            {"require_finding_details": True}
        )
        existing = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "workflow_state": "draft",
            "status": "open",
            "finding_details": "ok",
            "comments": "",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.get_by_key.return_value = dict(existing)
        mock_checklists.get_checklist.return_value = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
        }
        mock_grants.workspace_context.return_value = (
            {"_key": "ws1"},
            MagicMock(),
            [],
        )

        with self.assertRaises(ValueError):
            reviews_svc.update_review(
                MagicMock(),
                "rev1",
                {"finding_details": ""},
                "writer",
                {
                    "user": "writer",
                    "capabilities": {"stig_write": True},
                },
            )


class ReviewSubmitEnforcementTests(unittest.TestCase):
    def _strict_policy(self):
        return req_svc.normalize_policy({"require_finding_details": True})

    def _draft_review(self, **kwargs):
        base = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "workflow_state": "draft",
            "status": "open",
            "finding_details": "",
            "comments": "",
        }
        base.update(kwargs)
        return base

    @patch.object(reviews_svc, "review_requirements_svc")
    @patch.object(reviews_svc, "kv_client")
    @patch.object(reviews_svc, "grants_svc")
    @patch.object(reviews_svc, "checklists_svc")
    def test_submit_rejects_incomplete(
        self, mock_checklists, mock_grants, mock_kv, mock_req
    ):
        mock_req.get_policy.return_value = self._strict_policy()
        existing = self._draft_review()
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.get_by_key.return_value = dict(existing)
        mock_checklists.get_checklist.return_value = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
        }
        mock_grants.workspace_context.return_value = (
            {"_key": "ws1"},
            MagicMock(can_write=True),
            [],
        )

        with self.assertRaises(ValueError):
            reviews_svc.submit_review(
                MagicMock(),
                "rev1",
                "writer",
                {"user": "writer", "capabilities": {"stig_write": True}},
            )

    @patch.object(reviews_svc, "submit_review")
    def test_batch_workflow_submit_surfaces_errors(self, mock_submit):
        mock_submit.side_effect = ValueError(
            "cannot submit an incomplete review: Finding details are required"
        )
        result = reviews_svc.batch_workflow(
            MagicMock(),
            "submit",
            ["rev1"],
            "writer",
            {"user": "writer", "capabilities": {"stig_write": True}},
        )
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["errors"][0]["code"], "invalid")


if __name__ == "__main__":
    unittest.main()
