"""Unit tests for review history persistence and REST."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import types

if "splunk" not in sys.modules:
    persistconn = types.ModuleType("splunk.persistconn")
    application = types.ModuleType("splunk.persistconn.application")

    class PersistentServerConnectionApplication:  # noqa: D101
        def __init__(self, *args, **kwargs):
            pass

    application.PersistentServerConnectionApplication = (
        PersistentServerConnectionApplication
    )
    persistconn.application = application
    splunk = types.ModuleType("splunk")
    splunk.persistconn = persistconn
    sys.modules["splunk"] = splunk
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application

from services import checklists as checklists_svc  # noqa: E402
from services import collections as collections_svc  # noqa: E402
from services import review_history as history_svc  # noqa: E402
from services import reviews as reviews_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


def _scoped_access(host_ids):
    return history_svc.access.WorkspaceAccess(
        can_read=True,
        can_write=False,
        manage_grants=False,
        edit_collection=False,
        edit_access_principals=False,
        grant_role="restricted",
        acl_host_ids=set(host_ids),
        acl_baseline_ids=None,
        acl_label_ids=None,
        admin_bypass=False,
    )


class ReviewHistoryLogicTests(unittest.TestCase):
    def test_no_row_when_no_material_change(self):
        before = {
            "_key": "r1",
            "status": "open",
            "finding_details": "x",
            "comments": "",
            "workflow_state": "draft",
            "ingest_lock": False,
        }
        after = dict(before)
        after["updated_at"] = 99
        after["updated_by"] = "bob"
        self.assertFalse(history_svc.has_material_change(before, after))
        service = MagicMock()
        with patch.object(history_svc.kv_client, "insert_record") as mock_insert:
            result = history_svc.record_review_change(
                service, before, after, "bob", action="update"
            )
        self.assertIsNone(result)
        mock_insert.assert_not_called()

    def test_append_on_status_patch_via_update_review(self):
        service = MagicMock()
        session = {"user": "writer", "capabilities": {"stig_write": True}}
        existing = {
            "_key": "rev1",
            "checklist_id": "cl1",
            "status": "not_reviewed",
            "finding_details": "",
            "comments": "note",
            "workflow_state": "draft",
            "ingest_lock": False,
        }
        stored = {**existing, "status": "open", "updated_by": "writer"}

        with patch.object(reviews_svc, "kv_client") as mock_kv, patch.object(
            reviews_svc, "grants_svc"
        ) as mock_grants, patch.object(
            reviews_svc, "checklists_svc"
        ) as mock_cl, patch.object(
            reviews_svc, "review_requirements_svc"
        ) as mock_req, patch.object(
            reviews_svc, "review_history_svc"
        ) as mock_hist, patch.object(reviews_svc, "audit") as mock_audit:
            mock_audit.log_event = MagicMock()
            coll = MagicMock()
            mock_kv.get_collection.return_value = coll
            mock_kv.get_by_key.return_value = dict(existing)
            mock_kv.update_record.return_value = stored
            mock_kv.kv_record.side_effect = lambda r: r
            mock_grants.workspace_context.return_value = (
                {"_key": "ws1"},
                MagicMock(),
                [],
            )
            mock_cl.get_checklist.return_value = {
                "_key": "cl1",
                "stig_collection_id": "ws1",
            }
            mock_req.get_policy.return_value = mock_req.default_policy()

            reviews_svc.update_review(
                service, "rev1", {"status": "open"}, "writer", session
            )
            mock_hist.record_review_change.assert_called_once()
            args = mock_hist.record_review_change.call_args
            self.assertEqual(args[0][1]["status"], "not_reviewed")
            self.assertEqual(args[0][2]["status"], "open")
            self.assertEqual(args[1]["action"], "update")

    def test_list_review_history_sorted_newest_first(self):
        service = MagicMock()
        session = {"user": "alice", "capabilities": {"stig_read": True}}
        rows = [
            {"_key": "h1", "review_id": "r1", "created_at": 10, "summary": "old"},
            {"_key": "h2", "review_id": "r1", "created_at": 20, "summary": "new"},
        ]
        with patch.object(
            history_svc, "_require_visible_review", return_value={"_key": "r1"}
        ), patch.object(history_svc.kv_client, "get_collection") as mock_gc, patch.object(
            history_svc.kv_client, "query_all", return_value=rows
        ):
            mock_gc.return_value = MagicMock()
            out = history_svc.list_review_history(service, "r1", session)
        self.assertEqual(out["history"][0]["summary"], "new")
        self.assertEqual(out["pagination"]["total"], 2)

    def test_list_review_history_404_when_checklist_not_visible(self):
        service = MagicMock()
        session = {"user": "restricted", "capabilities": {"stig_read": True}}
        with patch.object(
            history_svc,
            "_require_visible_review",
            side_effect=KeyError("r-secret"),
        ):
            with self.assertRaises(KeyError):
                history_svc.list_review_history(service, "r-secret", session)

    def test_require_visible_review_denies_out_of_scope_host(self):
        service = MagicMock()
        session = {"user": "restricted", "capabilities": {"stig_read": True}}
        review = {
            "_key": "r1",
            "checklist_id": "cl1",
            "baseline_id": "b1",
            "host_id": "h2",
        }
        checklist = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
            "host_id": "h2",
            "baseline_id": "b1",
        }
        reviews_coll = MagicMock()
        with patch.object(history_svc.kv_client, "get_collection", return_value=reviews_coll), patch.object(
            history_svc.kv_client, "get_by_key", return_value=review
        ), patch.object(
            history_svc.checklists_svc, "get_checklist", return_value=checklist
        ), patch.object(
            history_svc.grants_svc,
            "workspace_context",
            return_value=({"_key": "ws1"}, _scoped_access(["h1"]), []),
        ), patch.object(history_svc, "_host_by_id_for_labels", return_value={}):
            with self.assertRaises(KeyError):
                history_svc._require_visible_review(service, "r1", session)

    def test_collection_history_filters_by_acl_host_ids(self):
        service = MagicMock()
        session = {"user": "restricted", "capabilities": {"stig_read": True}}
        rows = [
            {
                "_key": "a",
                "stig_collection_id": "ws1",
                "host_id": "h1",
                "baseline_id": "b1",
                "rule_id": "V-1",
                "created_at": 5,
            },
            {
                "_key": "b",
                "stig_collection_id": "ws1",
                "host_id": "h2",
                "baseline_id": "b1",
                "rule_id": "V-2",
                "created_at": 6,
            },
        ]
        with patch.object(
            history_svc.collections_svc, "get_collection", return_value={"_key": "ws1", "name": "Lab"}
        ), patch.object(history_svc.grants_svc, "query_grants", return_value=[]), patch.object(
            history_svc.access, "user_can_read_collection", return_value=True
        ), patch.object(
            history_svc.grants_svc,
            "workspace_context",
            return_value=({"_key": "ws1"}, _scoped_access(["h1"]), []),
        ), patch.object(history_svc, "_host_by_id_for_labels", return_value={}), patch.object(
            history_svc.kv_client, "get_collection"
        ), patch.object(history_svc.kv_client, "query_all", return_value=rows):
            out = history_svc.list_collection_review_history(service, "ws1", session)
        self.assertEqual(len(out["history"]), 1)
        self.assertEqual(out["history"][0]["host_id"], "h1")

    def test_collection_history_filters_host_and_rule(self):
        service = MagicMock()
        session = {"user": "alice", "capabilities": {"stig_read": True}}
        rows = [
            {
                "_key": "a",
                "stig_collection_id": "ws1",
                "host_id": "h1",
                "baseline_id": "b1",
                "rule_id": "V-1",
                "created_at": 5,
            },
            {
                "_key": "b",
                "stig_collection_id": "ws1",
                "host_id": "h2",
                "baseline_id": "b1",
                "rule_id": "V-2",
                "created_at": 6,
            },
        ]
        admin_ctx = history_svc.access.WorkspaceAccess(
            can_read=True,
            can_write=True,
            manage_grants=False,
            edit_collection=False,
            edit_access_principals=False,
            grant_role="owner",
            acl_host_ids=None,
            acl_baseline_ids=None,
            acl_label_ids=None,
            admin_bypass=True,
        )
        with patch.object(
            history_svc.collections_svc, "get_collection", return_value={"_key": "ws1", "name": "Lab"}
        ), patch.object(history_svc.grants_svc, "query_grants", return_value=[]), patch.object(
            history_svc.access, "user_can_read_collection", return_value=True
        ), patch.object(
            history_svc.grants_svc,
            "workspace_context",
            return_value=({"_key": "ws1"}, admin_ctx, []),
        ), patch.object(history_svc.kv_client, "get_collection"), patch.object(
            history_svc.kv_client, "query_all", return_value=rows
        ):
            out = history_svc.list_collection_review_history(
                service,
                "ws1",
                session,
                {"host_id": "h1", "rule_id": "V-1"},
            )
        self.assertEqual(len(out["history"]), 1)
        self.assertEqual(out["history"][0]["_key"], "a")

    def test_delete_history_for_collection(self):
        service = MagicMock()
        coll = MagicMock()
        rows = [{"_key": "h1"}, {"_key": "h2"}]
        with patch.object(history_svc.kv_client, "get_collection", return_value=coll), patch.object(
            history_svc.kv_client, "query_all", return_value=rows
        ), patch.object(history_svc.kv_client, "delete_record") as mock_delete:
            removed = history_svc.delete_history_for_collection(service, "ws1")
        self.assertEqual(removed, 2)
        self.assertEqual(mock_delete.call_count, 2)

    def test_cascade_delete_removes_review_history(self):
        service = MagicMock()
        with patch.object(collections_svc, "kv_client") as mock_kv, patch.object(
            collections_svc.review_history_svc,
            "delete_history_for_collection",
            return_value=3,
        ) as mock_hist_del:
            mock_kv.get_collection.return_value = MagicMock()
            mock_kv.query_all.return_value = []
            removed = collections_svc._cascade_delete_workspace_children(
                service, "ws1", "admin"
            )
        self.assertEqual(removed["review_history"], 3)
        mock_hist_del.assert_called_once_with(service, "ws1")


class ApplyReviewSeedsHistoryTests(unittest.TestCase):
    @patch.object(checklists_svc, "review_history_svc")
    @patch.object(checklists_svc, "kv_client")
    @patch.object(checklists_svc, "get_checklist")
    @patch.object(checklists_svc, "match_review_seed")
    def test_ingest_apply_records_history(
        self, mock_match, mock_get_cl, mock_kv, mock_hist
    ):
        rec = {
            "_key": "r1",
            "rule_id": "SV-1",
            "workflow_state": "draft",
            "status": "not_reviewed",
            "finding_details": "",
            "comments": "",
        }
        stored = {**rec, "status": "open", "finding_details": "scan"}
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.query_all.return_value = [rec]
        mock_kv.update_record.return_value = stored
        mock_kv.kv_record.side_effect = lambda r: r
        mock_get_cl.return_value = {"_key": "cl1", "stig_collection_id": "ws1"}
        mock_match.return_value = {"status": "open", "finding_details": "scan"}

        result = checklists_svc.apply_review_seeds(
            MagicMock(), "cl1", {}, "ingest", {}
        )
        self.assertEqual(result["updated"], 1)
        mock_hist.record_review_change.assert_called_once()
        self.assertEqual(mock_hist.record_review_change.call_args[1]["action"], "ingest")

    @patch.object(checklists_svc, "review_history_svc")
    @patch.object(checklists_svc, "kv_client")
    @patch.object(checklists_svc, "get_checklist")
    @patch.object(checklists_svc, "match_review_seed")
    def test_ingest_locked_skips_history(
        self, mock_match, mock_get_cl, mock_kv, mock_hist
    ):
        rec = {
            "_key": "r1",
            "rule_id": "SV-1",
            "ingest_lock": True,
            "workflow_state": "draft",
            "status": "open",
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.query_all.return_value = [rec]
        mock_get_cl.return_value = {"_key": "cl1"}
        mock_match.return_value = {"status": "not_a_finding"}

        result = checklists_svc.apply_review_seeds(
            MagicMock(), "cl1", {}, "ingest", {}
        )
        self.assertEqual(result["locked"], 1)
        mock_kv.update_record.assert_not_called()
        mock_hist.record_review_change.assert_not_called()


class ReviewHistoryRestTests(unittest.TestCase):
    def _session(self):
        return {
            "authtoken": "token",
            "user": "alice",
            "capabilities": {"stig_read": True},
        }

    def _dispatch(self, rest_path: str, query=None):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": self._session(),
            "rest_path": rest_path,
            "query": query or {},
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.review_history_svc, "list_review_history")
    def test_get_review_history_route(self, mock_list):
        mock_list.return_value = {"review_id": "r1", "history": [], "pagination": {}}
        resp = self._dispatch("/stig_reviews/r1/history")
        self.assertEqual(resp["status"], 200)
        mock_list.assert_called_once()

    @patch.object(stig_rest_handler.review_history_svc, "list_review_history")
    def test_review_history_acl_denial_is_404(self, mock_list):
        mock_list.side_effect = KeyError("r1")
        resp = self._dispatch("/stig_reviews/r1/history")
        self.assertEqual(resp["status"], 404)

    @patch.object(stig_rest_handler.review_history_svc, "list_collection_review_history")
    def test_collection_review_history_route(self, mock_list):
        mock_list.return_value = {
            "stig_collection_id": "ws1",
            "history": [],
            "pagination": {},
        }
        resp = self._dispatch("/stig_collections/ws1/review-history", {"limit": "10"})
        self.assertEqual(resp["status"], 200)
        mock_list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
