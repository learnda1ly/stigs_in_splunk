"""Effective access preview expands grant ACL to host × STIG checklists."""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import grants as grants_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _EffectiveAccessKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_collections": {},
            "stig_collection_grants": {},
            "stig_hosts": {},
            "stig_checklists": {},
            "stig_baselines": {},
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables.setdefault(name, {}))

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


def _owner_session(user: str = "owner") -> Dict[str, Any]:
    return {
        "user": user,
        "roles": [],
        "capabilities": {"stig_read": True, "stig_write": True},
    }


def _patch_kv(kv: _EffectiveAccessKv):
    modules = (
        "services.grants.kv_client",
        "services.collections.kv_client",
        "services.baselines.kv_client",
    )
    patches = []
    for mod in modules:
        patches.append(patch(f"{mod}.get_collection", side_effect=kv.get_collection))
        patches.append(patch(f"{mod}.query_all", side_effect=kv.query_all))
        patches.append(patch(f"{mod}.get_by_key", side_effect=kv.get_by_key))
    return patches


class TestEffectiveAccessPreview(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _EffectiveAccessKv()
        self.ws = {
            "_key": "ws1",
            "name": "Lab",
            "access_principals": "[]",
        }
        self.kv.tables["stig_collections"]["ws1"] = self.ws
        self.kv.tables["stig_hosts"]["h1"] = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "hostname": "alpha",
            "label_ids": "[]",
        }
        self.kv.tables["stig_hosts"]["h2"] = {
            "_key": "h2",
            "stig_collection_id": "ws1",
            "hostname": "beta",
            "label_ids": "[]",
        }
        self.kv.tables["stig_baselines"]["b1"] = {
            "_key": "b1",
            "stig_id": "U_RHEL_9",
            "title": "RHEL 9 STIG",
            "version": "V1R1",
        }
        self.kv.tables["stig_baselines"]["b2"] = {
            "_key": "b2",
            "stig_id": "U_WIN_11",
            "title": "Windows 11 STIG",
            "version": "V1R1",
        }
        self.kv.tables["stig_checklists"]["cl1"] = {
            "_key": "cl1",
            "stig_collection_id": "ws1",
            "host_id": "h1",
            "baseline_id": "b1",
        }
        self.kv.tables["stig_checklists"]["cl2"] = {
            "_key": "cl2",
            "stig_collection_id": "ws1",
            "host_id": "h1",
            "baseline_id": "b2",
        }
        self.kv.tables["stig_checklists"]["cl3"] = {
            "_key": "cl3",
            "stig_collection_id": "ws1",
            "host_id": "h2",
            "baseline_id": "b2",
        }
        self.kv.tables["stig_collection_grants"]["g_owner"] = {
            "_key": "g_owner",
            "stig_collection_id": "ws1",
            "principal": "user:owner",
            "grant_role": "owner",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }
        self.kv.tables["stig_collection_grants"]["g_narrow"] = {
            "_key": "g_narrow",
            "stig_collection_id": "ws1",
            "principal": "user:narrow",
            "grant_role": "restricted",
            "acl_host_ids": '["h1"]',
            "acl_baseline_ids": '["b1"]',
            "acl_labels": "[]",
        }
        self.kv.tables["stig_collection_grants"]["g_full"] = {
            "_key": "g_full",
            "stig_collection_id": "ws1",
            "principal": "user:member",
            "grant_role": "member",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }
        self.patches = _patch_kv(self.kv)
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_restricted_grant_expands_to_acl_intersection(self) -> None:
        preview = grants_svc.effective_access_for_grant(
            self.service, "ws1", "g_narrow", _owner_session()
        )
        self.assertEqual(preview["principal"], "user:narrow")
        self.assertEqual(preview["summary"]["host_count"], 1)
        self.assertEqual(preview["summary"]["checklist_count"], 1)
        self.assertEqual(preview["hosts"][0]["host_id"], "h1")
        self.assertEqual(len(preview["hosts"][0]["checklists"]), 1)
        self.assertEqual(preview["hosts"][0]["checklists"][0]["baseline_id"], "b1")

    def test_member_grant_expands_to_entire_collection(self) -> None:
        preview = grants_svc.effective_access_for_grant(
            self.service, "ws1", "g_full", _owner_session()
        )
        self.assertEqual(preview["summary"]["host_count"], 2)
        self.assertEqual(preview["summary"]["checklist_count"], 3)
        self.assertEqual(preview["summary"]["baseline_count"], 2)

    def test_principal_query_matches_grant_row(self) -> None:
        preview = grants_svc.effective_access_for_principal(
            self.service, "ws1", "user:narrow", _owner_session()
        )
        self.assertEqual(preview["grant_id"], "g_narrow")
        self.assertEqual(preview["summary"]["checklist_count"], 1)

    def test_permission_denied_without_manage_grants(self) -> None:
        self.kv.tables["stig_collection_grants"]["g_reader"] = {
            "_key": "g_reader",
            "stig_collection_id": "ws1",
            "principal": "user:reader",
            "grant_role": "member",
            "acl_host_ids": "[]",
            "acl_baseline_ids": "[]",
            "acl_labels": "[]",
        }
        with self.assertRaises(PermissionError):
            grants_svc.effective_access_for_grant(
                self.service, "ws1", "g_narrow", _owner_session("reader")
            )


if __name__ == "__main__":
    unittest.main()
