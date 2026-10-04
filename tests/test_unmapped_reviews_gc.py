"""Unmapped stig_reviews GC: service logic and admin REST."""

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

from services import unmapped_reviews as unmapped_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _UnmappedGcKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_baselines": {},
            "stig_baseline_rules": {},
            "stig_checklists": {},
            "stig_reviews": {},
            "stig_review_history": {},
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables[name])

    def query_all(
        self, coll: _MemColl, query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query = query or {}
        out: List[Dict[str, Any]] = []
        for key, rec in coll._rows.items():
            row = dict(rec)
            row.setdefault("_key", key)
            if all(row.get(k) == v for k, v in query.items()):
                out.append(row)
        return out

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        rec = coll._rows.get(key)
        if rec is None:
            return None
        row = dict(rec)
        row.setdefault("_key", key)
        return row

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)


def _patch_unmapped_kv(kv: _UnmappedGcKv):
    return (
        patch(
            "services.unmapped_reviews.kv_client.get_collection",
            side_effect=kv.get_collection,
        ),
        patch(
            "services.unmapped_reviews.kv_client.query_all",
            side_effect=kv.query_all,
        ),
        patch(
            "services.unmapped_reviews.kv_client.get_by_key",
            side_effect=kv.get_by_key,
        ),
        patch(
            "services.unmapped_reviews.kv_client.delete_record",
            side_effect=kv.delete_record,
        ),
        patch(
            "services.unmapped_reviews.baselines_svc.list_baselines",
            side_effect=lambda _s: list(kv.tables["stig_baselines"].values()),
        ),
    )


class TestUnmappedReviewsGcService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _UnmappedGcKv()
        self.kv.tables["stig_baselines"]["b1"] = {
            "_key": "b1",
            "stig_id": "Example_STIG",
        }
        self.kv.tables["stig_baseline_rules"]["r1"] = {
            "_key": "r1",
            "baseline_id": "b1",
            "rule_id": "SV-1",
            "group_id": "V-1",
        }
        self.kv.tables["stig_checklists"]["cl1"] = {
            "_key": "cl1",
            "baseline_id": "b1",
            "stig_collection_id": "ws1",
            "host_id": "h1",
        }
        self.kv.tables["stig_reviews"]["mapped"] = {
            "_key": "mapped",
            "checklist_id": "cl1",
            "baseline_id": "b1",
            "rule_id": "SV-1",
            "group_id": "V-1",
            "status": "open",
        }
        self.patches = _patch_unmapped_kv(self.kv)
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()

    def test_mapped_review_not_listed(self):
        report = unmapped_svc.gc_unmapped_reviews(
            self.service, "admin", execute=False
        )
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["unmapped_count"], 0)
        self.assertEqual(report["unmapped"], [])

    @patch("services.unmapped_reviews.audit.log_event")
    def test_rule_dropped_review_unmapped_and_deleted(self, mock_audit):
        self.kv.tables["stig_reviews"]["orphan_rule"] = {
            "_key": "orphan_rule",
            "checklist_id": "cl1",
            "baseline_id": "b1",
            "rule_id": "SV-99",
            "group_id": "V-99",
            "status": "open",
        }
        self.kv.tables["stig_review_history"]["h1"] = {
            "_key": "h1",
            "review_id": "orphan_rule",
        }

        dry = unmapped_svc.gc_unmapped_reviews(
            self.service, "admin", execute=False
        )
        self.assertEqual(dry["unmapped_count"], 1)
        self.assertEqual(dry["unmapped"][0]["reason"], "missing_rule")
        self.assertIn("mapped", self.kv.tables["stig_reviews"])
        self.assertIn("orphan_rule", self.kv.tables["stig_reviews"])

        report = unmapped_svc.gc_unmapped_reviews(
            self.service, "admin", execute=True
        )
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["deleted_count"], 1)
        self.assertIn("mapped", self.kv.tables["stig_reviews"])
        self.assertNotIn("orphan_rule", self.kv.tables["stig_reviews"])
        self.assertNotIn("h1", self.kv.tables["stig_review_history"])
        mock_audit.assert_called_once()
        self.assertEqual(mock_audit.call_args[0][0], "gc_unmapped_reviews")

    @patch("services.unmapped_reviews.audit.log_event")
    def test_missing_checklist_review_unmapped(self, mock_audit):
        self.kv.tables["stig_reviews"]["orphan_cl"] = {
            "_key": "orphan_cl",
            "checklist_id": "gone",
            "baseline_id": "b1",
            "rule_id": "SV-1",
            "group_id": "V-1",
        }
        found = unmapped_svc.find_unmapped_reviews(self.service)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["_key"], "orphan_cl")

        report = unmapped_svc.gc_unmapped_reviews(
            self.service, "admin", execute=True
        )
        self.assertEqual(report["deleted_count"], 1)
        mock_audit.assert_called_once()

    def test_collection_scope_filters(self):
        self.kv.tables["stig_checklists"]["cl2"] = {
            "_key": "cl2",
            "baseline_id": "b1",
            "stig_collection_id": "ws2",
            "host_id": "h2",
        }
        self.kv.tables["stig_reviews"]["other_ws"] = {
            "_key": "other_ws",
            "checklist_id": "cl2",
            "baseline_id": "b1",
            "rule_id": "SV-99",
            "group_id": "V-99",
        }
        scoped = unmapped_svc.find_unmapped_reviews(
            self.service, stig_collection_id="ws1"
        )
        self.assertEqual(scoped, [])
        scoped_ws2 = unmapped_svc.find_unmapped_reviews(
            self.service, stig_collection_id="ws2"
        )
        self.assertEqual(len(scoped_ws2), 1)


class TestUnmappedReviewsGcRest(unittest.TestCase):
    def _dispatch(
        self,
        method: str,
        rest_path: str,
        *,
        capabilities=None,
        query=None,
        body=None,
    ):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": {
                "authtoken": "token",
                "user": "admin",
                "capabilities": capabilities
                or {"stig_read": True, "stig_admin": True},
            },
            "rest_path": rest_path,
            "query": query or [],
        }
        if body is not None:
            payload["payload"] = body
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.unmapped_reviews_svc, "gc_unmapped_reviews")
    def test_get_report_admin(self, mock_gc):
        mock_gc.return_value = {"dry_run": True, "unmapped_count": 0, "unmapped": []}
        resp = self._dispatch("GET", "stig_reviews/gc_unmapped")
        self.assertEqual(resp["status"], 200)
        mock_gc.assert_called_once()
        self.assertFalse(mock_gc.call_args.kwargs.get("execute"))

    @patch.object(stig_rest_handler.unmapped_reviews_svc, "gc_unmapped_reviews")
    def test_post_execute_with_confirm(self, mock_gc):
        mock_gc.return_value = {"dry_run": False, "deleted_count": 1}
        resp = self._dispatch(
            "POST",
            "stig_reviews/gc_unmapped",
            body={"confirm": True},
        )
        self.assertEqual(resp["status"], 200)
        self.assertTrue(mock_gc.call_args.kwargs.get("execute"))

    def test_non_admin_denied(self):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": {
                "authtoken": "token",
                "user": "reader",
                "capabilities": {"stig_read": True, "stig_write": True},
            },
            "rest_path": "stig_reviews/gc_unmapped",
            "query": [],
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)


if __name__ == "__main__":
    unittest.main()
