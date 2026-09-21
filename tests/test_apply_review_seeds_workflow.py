"""Ingest must not overwrite submitted/accepted reviews."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import checklists as checklists_svc  # noqa: E402


class ApplyReviewSeedsWorkflowTests(unittest.TestCase):
    @patch.object(checklists_svc, "kv_client")
    @patch.object(checklists_svc, "get_checklist")
    @patch.object(checklists_svc, "match_review_seed")
    def test_skips_submitted_review(self, mock_match, mock_get_cl, mock_kv):
        rec = {
            "_key": "r1",
            "rule_id": "SV-1",
            "workflow_state": "submitted",
            "status": "open",
            "finding_details": "kept",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.query_all.return_value = [rec]
        mock_get_cl.return_value = {"_key": "cl1"}
        mock_match.return_value = {"status": "not_a_finding", "finding_details": "new"}

        result = checklists_svc.apply_review_seeds(
            MagicMock(), "cl1", {}, "ingest", {}
        )
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["locked"], 1)
        mock_kv.update_record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
