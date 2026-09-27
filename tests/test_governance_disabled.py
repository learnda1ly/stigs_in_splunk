"""Governance toggle: editable reviews and workflow API guards."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import review_workflow  # noqa: E402
from services import reviews as reviews_svc  # noqa: E402
from services import review_requirements as req_svc  # noqa: E402
from services import settings as settings_svc  # noqa: E402


class GovernanceDisabledTests(unittest.TestCase):
    def test_defaults_governance_on(self):
        self.assertTrue(settings_svc.is_governance_enabled({}))
        self.assertTrue(settings_svc.is_governance_enabled({"governance_enabled": "1"}))
        self.assertFalse(settings_svc.is_governance_enabled({"governance_enabled": "0"}))

    def test_workflow_editable_when_governance_off(self):
        rec = {"workflow_state": "submitted", "status": "open"}
        self.assertFalse(review_workflow.is_editable(rec, governance_enabled=True))
        self.assertTrue(review_workflow.is_editable(rec, governance_enabled=False))

    def test_governance_open_finding_when_disabled(self):
        accepted = {"status": "open", "workflow_state": "accepted"}
        self.assertFalse(
            review_workflow.is_governance_open_finding(accepted, governance_enabled=True)
        )
        self.assertTrue(
            review_workflow.is_governance_open_finding(accepted, governance_enabled=False)
        )

    @patch.object(reviews_svc, "settings_svc")
    @patch.object(reviews_svc, "kv_client")
    @patch.object(reviews_svc, "grants_svc")
    @patch.object(reviews_svc, "checklists_svc")
    def test_patch_allowed_when_submitted_and_governance_off(
        self, mock_checklists, mock_grants, mock_kv, mock_settings
    ):
        mock_settings.get_settings.return_value = {"governance_enabled": False}
        mock_settings.is_governance_enabled.return_value = False

        existing = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "workflow_state": "submitted",
            "finding_details": "a",
            "status": "open",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.get_by_key.return_value = existing
        mock_kv.update_record.return_value = {
            **existing,
            "finding_details": "b",
        }
        mock_kv.kv_record.side_effect = lambda r: r

        mock_checklists.get_checklist.return_value = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
        }
        mock_grants.workspace_context.return_value = (
            {"_key": "ws1"},
            MagicMock(),
            [],
        )

        session = {
            "user": "writer",
            "roles": [],
            "capabilities": {"stig_read": True, "stig_write": True},
        }

        with patch.object(reviews_svc, "review_requirements_svc") as mock_req:
            mock_req.default_policy.return_value = req_svc.default_policy()
            mock_req.get_policy.return_value = req_svc.default_policy()
            result = reviews_svc.update_review(
                MagicMock(),
                "rev1",
                {"finding_details": "b"},
                "writer",
                session,
            )
        self.assertEqual(result["finding_details"], "b")

    @patch.object(reviews_svc, "settings_svc")
    @patch.object(reviews_svc, "kv_client")
    def test_workflow_action_rejected_when_governance_off(
        self, mock_kv, mock_settings
    ):
        mock_settings.get_settings.return_value = {"governance_enabled": False}
        mock_settings.is_governance_enabled.return_value = False
        mock_kv.get_collection.return_value = MagicMock()

        with self.assertRaises(ValueError):
            reviews_svc.submit_review(
                MagicMock(),
                "rev1",
                "writer",
                {"user": "writer", "capabilities": {"stig_write": True}},
            )


if __name__ == "__main__":
    unittest.main()
