"""Orphan stig_baseline_rules GC: service logic and admin REST."""

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

from services import baselines as baselines_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _OrphanGcKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
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
        for key, rec in coll._rows.items():
            row = dict(rec)
            row.setdefault("_key", key)
            if all(row.get(k) == v for k, v in query.items()):
                out.append(row)
        return out

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)


def _patch_baselines_kv(kv: _OrphanGcKv):
    return (
        patch(
            "services.baselines.kv_client.get_collection",
            side_effect=kv.get_collection,
        ),
        patch("services.baselines.kv_client.query_all", side_effect=kv.query_all),
        patch(
            "services.baselines.kv_client.delete_record",
            side_effect=kv.delete_record,
        ),
    )


class TestOrphanBaselineRulesGcService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MagicMock()
        self.kv = _OrphanGcKv()
        self.kv.tables["stig_baselines"]["b1"] = {
            "_key": "b1",
            "stig_id": "Example_STIG",
        }
        self.kv.tables["stig_baseline_rules"]["good"] = {
            "_key": "good",
            "baseline_id": "b1",
            "rule_id": "SV-1",
            "group_id": "V-1",
        }
        self.patches = _patch_baselines_kv(self.kv)
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()

    def test_no_orphans_empty_report(self):
        report = baselines_svc.gc_orphan_baseline_rules(
            self.service, "admin", execute=False
        )
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["orphan_count"], 0)
        self.assertEqual(report["orphans"], [])
        self.assertEqual(report["deleted_count"], 0)

    @patch("services.baselines.audit.log_event")
    def test_orphans_detected(self, mock_audit):
        self.kv.tables["stig_baseline_rules"]["orph1"] = {
            "_key": "orph1",
            "baseline_id": "gone",
            "rule_id": "SV-9",
            "group_id": "V-9",
        }
        self.kv.tables["stig_baseline_rules"]["orph2"] = {
            "_key": "orph2",
            "baseline_id": "",
            "rule_id": "SV-2",
            "group_id": "V-2",
        }
        orphans = baselines_svc.find_orphan_baseline_rules(self.service)
        self.assertEqual(len(orphans), 2)
        report = baselines_svc.gc_orphan_baseline_rules(
            self.service, "admin", execute=False
        )
        self.assertEqual(report["orphan_count"], 2)
        self.assertEqual(len(self.kv.tables["stig_baseline_rules"]), 3)
        mock_audit.assert_not_called()

    @patch("services.baselines.audit.log_event")
    def test_execute_deletes_only_orphans(self, mock_audit):
        self.kv.tables["stig_baseline_rules"]["orph1"] = {
            "_key": "orph1",
            "baseline_id": "missing",
            "rule_id": "SV-9",
            "group_id": "V-9",
        }
        report = baselines_svc.gc_orphan_baseline_rules(
            self.service, "admin", execute=True
        )
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["deleted_count"], 1)
        self.assertIn("good", self.kv.tables["stig_baseline_rules"])
        self.assertNotIn("orph1", self.kv.tables["stig_baseline_rules"])
        mock_audit.assert_called_once()
        self.assertEqual(mock_audit.call_args[0][0], "gc_orphan_rules")

    @patch("services.baselines.audit.log_event")
    def test_execute_with_no_orphans_does_not_audit(self, mock_audit):
        report = baselines_svc.gc_orphan_baseline_rules(
            self.service, "admin", execute=True
        )
        self.assertFalse(report["dry_run"])
        self.assertEqual(report["deleted_count"], 0)
        mock_audit.assert_not_called()

    @patch("services.baselines.audit.log_event")
    @patch("services.baselines.find_orphan_baseline_rules")
    def test_execute_skips_orphans_without_key(
        self, mock_find, mock_audit
    ):
        mock_find.return_value = [
            {"baseline_id": "gone", "rule_id": "SV-1", "group_id": "V-1"}
        ]
        report = baselines_svc.gc_orphan_baseline_rules(
            self.service, "admin", execute=True
        )
        self.assertEqual(report["orphan_count"], 1)
        self.assertEqual(report["deleted_count"], 0)
        self.assertEqual(report["skipped_no_key_count"], 1)
        mock_audit.assert_not_called()

    def test_parse_execute_flag_defaults_dry_run(self):
        self.assertFalse(baselines_svc.parse_orphan_gc_execute_flag({}, {}))
        self.assertFalse(
            baselines_svc.parse_orphan_gc_execute_flag({"dry_run": "true"}, {})
        )
        self.assertTrue(
            baselines_svc.parse_orphan_gc_execute_flag({"dry_run": "false"}, {})
        )
        self.assertTrue(
            baselines_svc.parse_orphan_gc_execute_flag({}, {"confirm": True})
        )


class TestOrphanBaselineRulesGcRest(unittest.TestCase):
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

    @patch.object(stig_rest_handler.baselines_svc, "gc_orphan_baseline_rules")
    def test_get_report_admin(self, mock_gc):
        mock_gc.return_value = {"dry_run": True, "orphan_count": 0, "orphans": []}
        resp = self._dispatch("GET", "stig_baselines/gc_orphan_rules")
        self.assertEqual(resp["status"], 200)
        mock_gc.assert_called_once()
        self.assertFalse(mock_gc.call_args.kwargs.get("execute"))

    @patch.object(stig_rest_handler.baselines_svc, "gc_orphan_baseline_rules")
    def test_post_dry_run_default(self, mock_gc):
        mock_gc.return_value = {"dry_run": True, "orphan_count": 1, "orphans": [{}]}
        resp = self._dispatch("POST", "stig_baselines/gc_orphan_rules", body={})
        self.assertEqual(resp["status"], 200)
        self.assertFalse(mock_gc.call_args.kwargs.get("execute"))

    @patch.object(stig_rest_handler.baselines_svc, "gc_orphan_baseline_rules")
    def test_post_execute_with_confirm(self, mock_gc):
        mock_gc.return_value = {"dry_run": False, "deleted_count": 1}
        resp = self._dispatch(
            "POST",
            "stig_baselines/gc_orphan_rules",
            body={"confirm": True},
        )
        self.assertEqual(resp["status"], 200)
        self.assertTrue(mock_gc.call_args.kwargs.get("execute"))

    def test_non_admin_post_denied(self):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "POST",
            "session": {
                "authtoken": "token",
                "user": "reader",
                "capabilities": {"stig_read": True, "stig_write": True},
            },
            "rest_path": "stig_baselines/gc_orphan_rules",
            "query": [],
            "payload": {},
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)

    def test_non_admin_get_denied(self):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": {
                "authtoken": "token",
                "user": "reader",
                "capabilities": {"stig_read": True, "stig_write": True},
            },
            "rest_path": "stig_baselines/gc_orphan_rules",
            "query": [],
        }
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 403)


if __name__ == "__main__":
    unittest.main()
