"""Cross-asset review peers list and copy_from REST."""

from __future__ import annotations

import json
import os
import sys
import types
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

if "splunk" not in sys.modules:
    persistconn = types.ModuleType("splunk.persistconn")
    application = types.ModuleType("splunk.persistconn.application")

    class PersistentServerConnectionApplication:  # noqa: D101
        def __init__(self, *args, **kwargs):
            pass

    application.PersistentServerConnectionApplication = (
        PersistentServerConnectionApplication
    )
    splunk = types.ModuleType("splunk")
    splunk.persistconn = persistconn
    sys.modules["splunk"] = splunk
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application

import access  # noqa: E402
from services import review_peers as peers_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _PeerKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_reviews": {},
            "stig_checklists": {},
            "stig_hosts": {},
            "stig_baselines": {},
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables[name])

    def query_all(
        self, coll: _MemColl, query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query = query or {}
        out: List[Dict[str, Any]] = []
        for rec in coll._rows.values():
            if all(rec.get(k) == v for k, v in query.items()):
                out.append(dict(rec))
        return out

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None


def _restricted_ctx(host_ids):
    return access.WorkspaceAccess(
        can_read=True,
        can_write=True,
        manage_grants=False,
        edit_collection=False,
        edit_access_principals=False,
        grant_role="restricted",
        acl_host_ids=set(host_ids),
        acl_baseline_ids=None,
        acl_label_ids=None,
        admin_bypass=False,
    )


class ReviewPeersLogicTests(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.session = {"user": "alice", "capabilities": {"stig_read": True, "stig_write": True}}
        self.kv = _PeerKv()
        self.kv.tables["stig_baselines"]["bl1"] = {
            "_key": "bl1",
            "stig_id": "RHEL_STIG",
            "version": "V1R1",
        }
        self.kv.tables["stig_baselines"]["bl2"] = {
            "_key": "bl2",
            "stig_id": "RHEL_STIG",
            "version": "V2R1",
        }
        self.kv.tables["stig_checklists"]["cl_anchor"] = {
            "_key": "cl_anchor",
            "stig_collection_id": "ws1",
            "host_id": "h1",
            "baseline_id": "bl1",
        }
        self.kv.tables["stig_checklists"]["cl_peer"] = {
            "_key": "cl_peer",
            "stig_collection_id": "ws1",
            "host_id": "h2",
            "baseline_id": "bl1",
        }
        self.kv.tables["stig_checklists"]["cl_peer_v2"] = {
            "_key": "cl_peer_v2",
            "stig_collection_id": "ws1",
            "host_id": "h2",
            "baseline_id": "bl2",
        }
        self.kv.tables["stig_checklists"]["cl_hidden"] = {
            "_key": "cl_hidden",
            "stig_collection_id": "ws1",
            "host_id": "h3",
            "baseline_id": "bl1",
        }
        self.kv.tables["stig_hosts"]["h1"] = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "hostname": "host-one",
        }
        self.kv.tables["stig_hosts"]["h2"] = {
            "_key": "h2",
            "stig_collection_id": "ws1",
            "hostname": "host-two",
        }
        self.kv.tables["stig_hosts"]["h3"] = {
            "_key": "h3",
            "stig_collection_id": "ws1",
            "hostname": "host-three",
        }
        self.kv.tables["stig_reviews"]["r_anchor"] = {
            "_key": "r_anchor",
            "checklist_id": "cl_anchor",
            "baseline_id": "bl1",
            "group_id": "V-1",
            "rule_id": "SV-1",
            "rule_version": "RHEL-08-010000",
            "status": "not_reviewed",
            "workflow_state": "draft",
        }
        self.kv.tables["stig_reviews"]["r_peer_v2"] = {
            "_key": "r_peer_v2",
            "checklist_id": "cl_peer_v2",
            "baseline_id": "bl2",
            "group_id": "V-1",
            "rule_id": "SV-1",
            "rule_version": "RHEL-08-010000",
            "status": "not_a_finding",
            "finding_details": "rev2 peer",
            "workflow_state": "draft",
        }
        self.kv.tables["stig_reviews"]["r_peer"] = {
            "_key": "r_peer",
            "checklist_id": "cl_peer",
            "baseline_id": "bl1",
            "group_id": "V-1",
            "rule_id": "SV-1",
            "rule_version": "RHEL-08-010000",
            "status": "open",
            "finding_details": "peer finding",
            "comments": "peer note",
            "workflow_state": "draft",
        }
        self.kv.tables["stig_reviews"]["r_hidden"] = {
            "_key": "r_hidden",
            "checklist_id": "cl_hidden",
            "baseline_id": "bl1",
            "group_id": "V-1",
            "rule_id": "SV-1",
            "rule_version": "RHEL-08-010000",
            "status": "open",
            "finding_details": "secret",
            "workflow_state": "draft",
        }

    def _patch_stack(self, visible_checklist_keys, host_ctx=None):
        visible = [
            self.kv.tables["stig_checklists"][k]
            for k in visible_checklist_keys
            if k in self.kv.tables["stig_checklists"]
        ]
        return (
            patch.object(peers_svc.kv_client, "get_collection", self.kv.get_collection),
            patch.object(peers_svc.kv_client, "query_all", self.kv.query_all),
            patch.object(peers_svc.kv_client, "get_by_key", self.kv.get_by_key),
            patch.object(
                peers_svc.review_history_svc,
                "_require_visible_review",
                return_value=dict(self.kv.tables["stig_reviews"]["r_anchor"]),
            ),
            patch.object(
                peers_svc.checklists_svc,
                "list_checklists",
                return_value=[dict(c) for c in visible],
            ),
            patch.object(
                peers_svc.checklists_svc,
                "get_checklist",
                side_effect=lambda _s, key, _sess, write=False: dict(
                    self.kv.tables["stig_checklists"].get(key) or {}
                )
                if key in self.kv.tables["stig_checklists"]
                else None,
            ),
            patch.object(
                peers_svc.baselines_svc,
                "get_baseline",
                side_effect=lambda _s, key: dict(self.kv.tables["stig_baselines"].get(key) or {})
                or None,
            ),
            patch.object(
                peers_svc.hosts_svc,
                "get_host",
                side_effect=lambda _s, key, _sess: dict(self.kv.tables["stig_hosts"].get(key) or {})
                if key in (host_ctx or {"h1", "h2", "h3"})
                else None,
            ),
        )

    def test_lists_peer_on_other_host(self):
        patches = self._patch_stack(["cl_anchor", "cl_peer"], {"h1", "h2"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            out = peers_svc.list_review_peers(self.service, "r_anchor", self.session)
        self.assertEqual(len(out["peers"]), 1)
        self.assertEqual(out["peers"][0]["review_id"], "r_peer")
        self.assertEqual(out["peers"][0]["hostname"], "host-two")
        self.assertIn("peer finding", out["peers"][0]["finding_details_snippet"])

    def test_acl_hides_out_of_scope_host(self):
        """Checklist may be listed, but host grant ACL drops the peer row."""
        patches = self._patch_stack(
            ["cl_anchor", "cl_peer", "cl_hidden"], {"h1", "h2"}
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            out = peers_svc.list_review_peers(self.service, "r_anchor", self.session)
        ids = {p["review_id"] for p in out["peers"]}
        self.assertIn("r_peer", ids)
        self.assertNotIn("r_hidden", ids)

    def test_peers_match_same_stig_id_different_baseline(self):
        patches = self._patch_stack(
            ["cl_anchor", "cl_peer_v2"], {"h1", "h2"}
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            out = peers_svc.list_review_peers(self.service, "r_anchor", self.session)
        ids = {p["review_id"] for p in out["peers"]}
        self.assertEqual(ids, {"r_peer_v2"})
        self.assertEqual(out["peers"][0]["baseline_id"], "bl2")

    def test_empty_peers_when_rule_id_missing(self):
        anchor = dict(self.kv.tables["stig_reviews"]["r_anchor"])
        anchor["rule_id"] = ""
        patches = self._patch_stack(["cl_anchor", "cl_peer"], {"h1", "h2"})
        with patches[0], patches[1], patches[2], patch.object(
            peers_svc.review_history_svc,
            "_require_visible_review",
            return_value=anchor,
        ), patches[4], patches[5], patches[6], patches[7]:
            out = peers_svc.list_review_peers(self.service, "r_anchor", self.session)
        self.assertEqual(out["peers"], [])
        self.assertEqual(out["rule_id"], "")

    def test_empty_peers_when_no_other_checklists(self):
        patches = self._patch_stack(["cl_anchor"], {"h1"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            out = peers_svc.list_review_peers(self.service, "r_anchor", self.session)
        self.assertEqual(out["peers"], [])

    @patch.object(peers_svc.reviews_svc, "update_review")
    def test_copy_from_peer_when_editable(self, mock_update):
        mock_update.return_value = {"_key": "r_anchor", "status": "open"}
        patches = self._patch_stack(["cl_anchor", "cl_peer"], {"h1", "h2"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            result = peers_svc.copy_from_peer(
                self.service, "r_anchor", "r_peer", "alice", self.session
            )
        mock_update.assert_called_once()
        patch_body = mock_update.call_args[0][2]
        self.assertEqual(patch_body["status"], "open")
        self.assertEqual(patch_body["finding_details"], "peer finding")
        self.assertEqual(result["copied_from"], "r_peer")

    @patch.object(peers_svc.reviews_svc, "update_review")
    def test_copy_rejects_non_editable(self, mock_update):
        mock_update.side_effect = PermissionError("not editable")
        patches = self._patch_stack(["cl_anchor", "cl_peer"], {"h1", "h2"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            with self.assertRaises(PermissionError):
                peers_svc.copy_from_peer(
                    self.service, "r_anchor", "r_peer", "alice", self.session
                )

    @patch.object(peers_svc.reviews_svc, "update_review")
    def test_copy_rejects_peer_out_of_scope(self, mock_update):
        patches = self._patch_stack(["cl_anchor", "cl_peer"], {"h1", "h2"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            with self.assertRaises(KeyError):
                peers_svc.copy_from_peer(
                    self.service, "r_anchor", "r_hidden", "alice", self.session
                )
        mock_update.assert_not_called()


class ReviewPeersRestTests(unittest.TestCase):
    def _session(self):
        return {
            "authtoken": "token",
            "user": "alice",
            "capabilities": {"stig_read": True, "stig_write": True},
        }

    def _dispatch(self, rest_path: str, method="GET", body=None):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": self._session(),
            "rest_path": rest_path,
            "query": {},
            "payload": json.dumps(body or {}),
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.review_peers_svc, "list_review_peers")
    def test_get_peers_route(self, mock_list):
        mock_list.return_value = {"review_id": "r1", "peers": []}
        resp = self._dispatch("/stig_reviews/r1/peers")
        self.assertEqual(resp["status"], 200)
        mock_list.assert_called_once()

    @patch.object(stig_rest_handler.review_peers_svc, "list_review_peers")
    def test_peers_acl_is_404(self, mock_list):
        mock_list.side_effect = KeyError("r1")
        resp = self._dispatch("/stig_reviews/r1/peers")
        self.assertEqual(resp["status"], 404)

    @patch.object(stig_rest_handler.review_peers_svc, "copy_from_peer")
    def test_copy_from_route(self, mock_copy):
        mock_copy.return_value = {"review": {"_key": "r1"}, "copied_from": "r2"}
        resp = self._dispatch("/stig_reviews/r1/copy_from/r2", method="POST")
        self.assertEqual(resp["status"], 200)
        mock_copy.assert_called_once()

    @patch.object(stig_rest_handler.review_peers_svc, "copy_from_peer")
    def test_copy_from_validation_maps_to_400(self, mock_copy):
        mock_copy.side_effect = ValueError("finding_details required")
        resp = self._dispatch("/stig_reviews/r1/copy_from/r2", method="POST")
        self.assertEqual(resp["status"], 400)

    def test_copy_from_rejects_put(self):
        resp = self._dispatch("/stig_reviews/r1/copy_from/r2", method="PUT")
        self.assertEqual(resp["status"], 405)


if __name__ == "__main__":
    unittest.main()
