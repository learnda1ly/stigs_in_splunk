"""Service-layer tests for review governance (accept without write, PATCH guards)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import reviews as reviews_svc  # noqa: E402


class ReviewWorkflowServiceTests(unittest.TestCase):
    def _session_reviewer(self):
        return {
            "user": "reviewer",
            "roles": [],
            "capabilities": {"stig_read": True},
        }

    def _session_writer(self):
        return {
            "user": "writer",
            "roles": [],
            "capabilities": {"stig_read": True, "stig_write": True},
        }

    @patch.object(reviews_svc, "kv_client")
    @patch.object(reviews_svc, "grants_svc")
    @patch.object(reviews_svc, "checklists_svc")
    def test_accept_without_workspace_write(
        self, mock_checklists, mock_grants, mock_kv
    ):
        existing = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "status": "open",
            "finding_details": "x",
            "workflow_state": "submitted",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.get_by_key.return_value = dict(existing)
        mock_kv.update_record.return_value = {
            **existing,
            "workflow_state": "accepted",
            "accepted_by": "reviewer",
        }
        mock_kv.kv_record.side_effect = lambda r: r

        mock_checklists.get_checklist.return_value = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
        }
        mock_grants.workspace_context.return_value = (
            {"_key": "ws1", "access_principals": "[]"},
            MagicMock(can_write=False, grant_role="manager"),
            [{"principal": "user:reviewer", "grant_role": "manager"}],
        )

        with patch.object(reviews_svc, "audit") as mock_audit:
            mock_audit.log_event = MagicMock()
            result = reviews_svc.accept_review(
                MagicMock(), "rev1", "reviewer", self._session_reviewer()
            )

        mock_checklists.get_checklist.assert_called_once()
        self.assertFalse(mock_checklists.get_checklist.call_args.kwargs.get("write"))
        self.assertEqual(result["workflow_state"], "accepted")

    @patch.object(reviews_svc, "kv_client")
    @patch.object(reviews_svc, "grants_svc")
    @patch.object(reviews_svc, "checklists_svc")
    def test_writer_without_accept_cannot_accept(
        self, mock_checklists, mock_grants, mock_kv
    ):
        existing = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "workflow_state": "submitted",
            "finding_details": "x",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.get_by_key.return_value = existing
        mock_checklists.get_checklist.return_value = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
        }
        mock_grants.workspace_context.return_value = (
            {"_key": "ws1", "access_principals": "[]"},
            MagicMock(can_write=True, grant_role="member"),
            [],
        )

        with self.assertRaises(PermissionError):
            reviews_svc.accept_review(
                MagicMock(), "rev1", "writer", self._session_writer()
            )

    @patch.object(reviews_svc, "kv_client")
    @patch.object(reviews_svc, "grants_svc")
    @patch.object(reviews_svc, "checklists_svc")
    def test_patch_blocked_when_submitted(
        self, mock_checklists, mock_grants, mock_kv
    ):
        existing = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "workflow_state": "submitted",
            "finding_details": "a",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.get_by_key.return_value = existing
        mock_checklists.get_checklist.return_value = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
        }
        mock_grants.workspace_context.return_value = (
            {"_key": "ws1"},
            MagicMock(),
            [],
        )

        with self.assertRaises(PermissionError):
            reviews_svc.update_review(
                MagicMock(),
                "rev1",
                {"finding_details": "b"},
                "writer",
                self._session_writer(),
            )

    def test_batch_workflow_enforces_max(self):
        ids = [str(i) for i in range(reviews_svc.MAX_BATCH_REVIEWS + 1)]
        with self.assertRaises(ValueError):
            reviews_svc.batch_workflow(
                MagicMock(), "submit", ids, "u", {}, reject_feedback=None
            )


if __name__ == "__main__":
    unittest.main()
