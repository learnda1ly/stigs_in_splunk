"""Service-level grant label ACL: reviews, metrics, findings, export, validation."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import access  # noqa: E402
from services import checklists as checklists_svc  # noqa: E402
from services import grants as grants_svc  # noqa: E402
from services import hosts as hosts_svc  # noqa: E402
from services import reporting as reporting_svc  # noqa: E402
from services import reviews as reviews_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _LabelAclKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {},
            "stig_collection_grants": {},
            "stig_hosts": {},
            "stig_labels": {},
            "stig_checklists": {},
            "stig_reviews": {},
            "stig_baselines": {},
            "stig_baseline_rules": {},
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        if name not in self.tables:
            raise KeyError(name)
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

    def update_record(self, coll: _MemColl, key: str, record: Dict[str, Any]) -> Dict[str, Any]:
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored


def _session(user: str, *, write: bool = False) -> Dict[str, Any]:
    caps = {"stig_read": True}
    if write:
        caps["stig_write"] = True
    return {"user": user, "roles": [], "capabilities": caps}


def _patch_kv(kv: _LabelAclKv):
    modules = (
        "services.collections.kv_client",
        "services.grants.kv_client",
        "services.hosts.kv_client",
        "services.labels.kv_client",
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
    patches.append(
        patch("services.hosts.kv_client.update_record", side_effect=kv.update_record)
    )
    return patches


class TestGrantLabelAclServices(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _LabelAclKv()
        self.ws = {
            "_key": "ws1",
            "name": "Lab",
            "access_principals": "[]",
        }
        self.kv.tables["stig_collections"]["ws1"] = self.ws
        self.kv.tables["stig_labels"]["lbl1"] = {
            "_key": "lbl1",
            "stig_collection_id": "ws1",
            "name": "Production",
        }
        self.kv.tables["stig_hosts"]["h1"] = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "hostname": "prod-01",
            "label_ids": '["lbl1"]',
        }
        self.kv.tables["stig_hosts"]["h2"] = {
            "_key": "h2",
            "stig_collection_id": "ws1",
            "hostname": "dev-01",
            "label_ids": "[]",
        }
        self.kv.tables["stig_checklists"]["cl1"] = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
            "host_id": "h1",
            "baseline_id": "base1",
        }
        self.kv.tables["stig_checklists"]["cl2"] = {
            "_key": "cl2",
            "stig_collection_id": "ws1",
            "host_id": "h2",
            "baseline_id": "base1",
        }
        self.kv.tables["stig_reviews"]["r1"] = {
            "_key": "r1",
            "checklist_id": "cl1",
            "baseline_id": "base1",
            "rule_id": "SV-1",
            "status": "open",
            "workflow_state": "draft",
        }
        self.kv.tables["stig_reviews"]["r2"] = {
            "_key": "r2",
            "checklist_id": "cl2",
            "baseline_id": "base1",
            "rule_id": "SV-1",
            "status": "open",
            "workflow_state": "draft",
        }
        self.kv.tables["stig_collection_grants"]["g1"] = {
            "_key": "g1",
            "stig_collection_id": "ws1",
            "principal": "user:bob",
            "grant_role": "restricted",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": '["lbl1"]',
        }
        self.kv.tables["stig_baselines"]["base1"] = {
            "_key": "base1",
            "stig_id": "Example_STIG",
            "title": "Example",
        }
        self.patches = _patch_kv(self.kv)
        self.patches.append(
            patch(
                "services.collections.ensure_default_collection",
                return_value=None,
            )
        )
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()

    def test_list_reviews_respects_label_acl(self) -> None:
        bob = _session("bob")
        rows = reviews_svc.list_reviews(
            self.service, bob, stig_collection_id="ws1"
        )
        ids = {r["_key"] for r in rows}
        self.assertEqual(ids, {"r1"})

    def test_collection_metrics_label_acl(self) -> None:
        bob = _session("bob")
        metrics = reporting_svc.collection_metrics(self.service, "ws1", bob)
        self.assertEqual(metrics["totals"]["hosts"], 1)
        self.assertEqual(metrics["totals"]["checklists"], 1)
        self.assertEqual(metrics["totals"]["reviews"], 1)

    def test_collection_findings_label_acl(self) -> None:
        bob = _session("bob")
        with patch("services.reporting.review_workflow.is_governance_open_finding", return_value=True):
            rows, _filters, _ctx = reporting_svc._list_collection_findings(
                self.service, "ws1", bob
            )
        checklist_ids = {row.get("checklist_id") for row in rows}
        self.assertEqual(checklist_ids, {"cl1"})

    def test_export_checklist_ids_label_acl(self) -> None:
        bob = _session("bob")
        ids = checklists_svc.checklist_ids_for_collection_export(
            self.service, "ws1", bob
        )
        self.assertEqual(ids, ["cl1"])

    def test_host_and_label_acl_composition(self) -> None:
        self.kv.tables["stig_collection_grants"]["g1"]["acl_host_ids"] = '["h1"]'
        self.kv.tables["stig_collection_grants"]["g1"]["acl_labels"] = '["lbl1"]'
        self.kv.tables["stig_hosts"]["h3"] = {
            "_key": "h3",
            "stig_collection_id": "ws1",
            "hostname": "prod-02",
            "label_ids": '["lbl1"]',
        }
        self.kv.tables["stig_checklists"]["cl3"] = {
            "_key": "cl3",
            "stig_collection_id": "ws1",
            "host_id": "h3",
            "baseline_id": "base1",
        }
        self.kv.tables["stig_reviews"]["r3"] = {
            "_key": "r3",
            "checklist_id": "cl3",
            "baseline_id": "base1",
            "rule_id": "SV-2",
            "status": "open",
            "workflow_state": "draft",
        }
        bob = _session("bob")
        rows = reviews_svc.list_reviews(
            self.service, bob, stig_collection_id="ws1"
        )
        self.assertEqual({r["_key"] for r in rows}, {"r1"})

    def test_host_patch_rejects_foreign_label(self) -> None:
        self.kv.tables["stig_labels"]["other"] = {
            "_key": "other",
            "stig_collection_id": "ws2",
            "name": "Other ws",
        }
        alice = _session("alice", write=True)
        self.kv.tables["stig_collection_grants"]["g2"] = {
            "_key": "g2",
            "stig_collection_id": "ws1",
            "principal": "user:alice",
            "grant_role": "owner",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }
        with self.assertRaises(ValueError):
            hosts_svc.update_host(
                self.service,
                "h1",
                {"label_ids": ["other"]},
                "alice",
                alice,
            )

    def test_grant_create_rejects_unknown_acl_label(self) -> None:
        owner = _session("owner", write=True)
        self.kv.tables["stig_collection_grants"]["g_owner"] = {
            "_key": "g_owner",
            "stig_collection_id": "ws1",
            "principal": "user:owner",
            "grant_role": "owner",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }
        with self.assertRaises(ValueError):
            grants_svc.create_grant(
                self.service,
                "ws1",
                {
                    "principal": "user:carol",
                    "grant_role": "restricted",
                    "acl_labels": ["does-not-exist"],
                },
                "owner",
                owner,
            )


if __name__ == "__main__":
    unittest.main()
