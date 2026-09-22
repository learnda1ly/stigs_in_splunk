"""Meta-collection metrics across grant-filtered workspaces."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import reporting as reporting_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _MetaKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {},
            "stig_collection_grants": {},
            "stig_hosts": {},
            "stig_checklists": {},
            "stig_reviews": {},
            "stig_baselines": {},
            "stig_baseline_rules": {},
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


def _session(user: str) -> Dict[str, Any]:
    return {"user": user, "roles": [], "capabilities": {"stig_read": True}}


def _patch_kv(kv: _MetaKv):
    modules = (
        "services.collections.kv_client",
        "services.grants.kv_client",
        "services.hosts.kv_client",
        "services.checklists.kv_client",
        "services.reviews.kv_client",
        "services.reporting.kv_client",
        "services.baselines.kv_client",
    )
    patches = []
    for mod in modules:
        patches.append(patch(f"{mod}.get_collection", side_effect=kv.get_collection))
        patches.append(patch(f"{mod}.query_all", side_effect=kv.query_all))
        patches.append(patch(f"{mod}.get_by_key", side_effect=kv.get_by_key))
    return patches


class TestMetaCollectionMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _MetaKv()
        self.kv.tables["stig_collections"]["ws1"] = {
            "_key": "ws1",
            "name": "Alpha",
            "access_principals": '["user:alice"]',
        }
        self.kv.tables["stig_collections"]["ws2"] = {
            "_key": "ws2",
            "name": "Bravo",
            "access_principals": '["user:bob"]',
        }
        for ws, host_key in (("ws1", "h1"), ("ws2", "h2")):
            self.kv.tables["stig_hosts"][host_key] = {
                "_key": host_key,
                "stig_collection_id": ws,
                "hostname": host_key,
            }
            cl_key = "cl_" + ws
            self.kv.tables["stig_checklists"][cl_key] = {
                "_key": cl_key,
                "stig_collection_id": ws,
                "host_id": host_key,
                "baseline_id": "base1",
            }
            self.kv.tables["stig_reviews"]["r_" + ws] = {
                "_key": "r_" + ws,
                "checklist_id": cl_key,
                "baseline_id": "base1",
                "rule_id": "SV-1",
                "group_id": "V-1",
                "status": "not_reviewed",
            }
        self.kv.tables["stig_baselines"]["base1"] = {
            "_key": "base1",
            "stig_id": "Example_STIG",
            "title": "Example",
        }
        self.patches = _patch_kv(self.kv)
        self.patches.append(
            patch("services.collections.ensure_default_collection", return_value=None)
        )
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()

    def test_alice_sees_only_granted_workspace(self) -> None:
        result = reporting_svc.meta_collection_metrics(self.service, _session("alice"))
        self.assertEqual(result["workspace_count"], 1)
        self.assertEqual(len(result["workspaces"]), 1)
        self.assertEqual(result["workspaces"][0]["stig_collection_id"], "ws1")
        self.assertEqual(result["summary"]["totals"]["hosts"], 1)
        self.assertEqual(result["summary"]["totals"]["reviews"], 1)

    def test_alice_never_sees_hidden_workspace_fields(self) -> None:
        result = reporting_svc.meta_collection_metrics(self.service, _session("alice"))
        payload = str(result)
        self.assertNotIn("ws2", payload)
        self.assertNotIn("Bravo", payload)
        ids = {w["stig_collection_id"] for w in result["workspaces"]}
        self.assertEqual(ids, {"ws1"})

    def test_admin_bypass_sees_both_and_rolls_up(self) -> None:
        admin = {
            "user": "admin",
            "roles": [],
            "capabilities": {"stig_read": True, "stig_admin": True},
        }
        result = reporting_svc.meta_collection_metrics(self.service, admin)
        self.assertEqual(result["workspace_count"], 2)
        self.assertEqual(result["summary"]["totals"]["hosts"], 2)
        self.assertEqual(result["summary"]["totals"]["reviews"], 2)
        self.assertEqual(result["summary"]["completion"]["not_reviewed"], 2)

    def test_empty_when_no_readable_workspaces(self) -> None:
        result = reporting_svc.meta_collection_metrics(self.service, _session("stranger"))
        self.assertEqual(result["workspace_count"], 0)
        self.assertEqual(result["workspaces"], [])
        self.assertEqual(result["summary"]["totals"]["hosts"], 0)

    def test_summary_endpoint_shape(self) -> None:
        summary = reporting_svc.meta_collection_metrics_summary(
            self.service, _session("alice")
        )
        self.assertIn("summary", summary)
        self.assertNotIn("workspaces", summary)
        self.assertNotIn("pagination", summary)
        self.assertEqual(summary["workspace_count"], 1)

    def test_summary_matches_full_org_when_workspaces_paginated(self) -> None:
        admin = {
            "user": "admin",
            "roles": [],
            "capabilities": {"stig_read": True, "stig_admin": True},
        }
        full = reporting_svc.meta_collection_metrics(self.service, admin)
        paged = reporting_svc.meta_collection_metrics(
            self.service, admin, {"limit": 1, "offset": 1}
        )
        self.assertEqual(paged["workspace_count"], 2)
        self.assertEqual(len(paged["workspaces"]), 1)
        self.assertEqual(paged["summary"]["totals"], full["summary"]["totals"])
        self.assertNotEqual(
            paged["workspaces"][0]["stig_collection_id"],
            full["workspaces"][0]["stig_collection_id"],
        )


if __name__ == "__main__":
    unittest.main()
