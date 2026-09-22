"""Baseline catalog reference APIs: rule / group / CCI lookup across revisions."""

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

from importers import xccdf  # noqa: E402
from services import baselines as baselines_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _RefKv:
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
        for rec in coll._rows.values():
            if all(rec.get(k) == v for k, v in query.items()):
                out.append(dict(rec))
        return out

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None


def _load_fixture_rules():
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")
    with open(fixture, "rb") as handle:
        meta, rules = xccdf.parse_xccdf(handle.read())
    return meta, rules


class TestBaselineReferenceServices(unittest.TestCase):
    def setUp(self):
        self.kv = _RefKv()
        self.meta, self.rules = _load_fixture_rules()
        self.baseline_a = {
            "_key": "base_v1",
            "stig_id": "Example_STIG",
            "version": "1",
            "title": "Example STIG v1",
        }
        self.baseline_b = {
            "_key": "base_v2",
            "stig_id": "Example_STIG",
            "version": "2",
            "title": "Example STIG v2",
        }
        self.kv.tables["stig_baselines"]["base_v1"] = self.baseline_a
        self.kv.tables["stig_baselines"]["base_v2"] = self.baseline_b
        rule = self.rules[0]
        self.kv.tables["stig_baseline_rules"]["rule_a"] = {
            "_key": "rule_a",
            "baseline_id": "base_v1",
            "group_id": rule["group_id"],
            "rule_id": rule["rule_id"],
            "rule_id_src": rule.get("rule_id_src") or "",
            "rule_version": rule["rule_version"],
            "severity": rule["severity"],
            "rule_title": rule["rule_title"],
            "group_title": rule.get("group_title") or "",
            "ccis": baselines_svc.dumps_json(rule.get("ccis") or []),
            "check_content_hash": rule["check_content_hash"],
        }
        self.kv.tables["stig_baseline_rules"]["rule_b"] = {
            "_key": "rule_b",
            "baseline_id": "base_v2",
            "group_id": rule["group_id"],
            "rule_id": rule["rule_id"],
            "rule_id_src": rule.get("rule_id_src") or "",
            "rule_version": rule["rule_version"],
            "severity": rule["severity"],
            "rule_title": rule["rule_title"] + " (rev 2)",
            "group_title": rule.get("group_title") or "",
            "ccis": baselines_svc.dumps_json(rule.get("ccis") or []),
            "check_content_hash": rule["check_content_hash"],
        }

    def _patch(self):
        return patch.multiple(
            baselines_svc.kv_client,
            get_collection=self.kv.get_collection,
            query_all=self.kv.query_all,
            get_by_key=self.kv.get_by_key,
        )

    def test_find_rule_ref_across_baselines(self):
        with self._patch():
            matches = baselines_svc.find_catalog_rules_by_ref(self.kv, "SV-000001")
        self.assertEqual(len(matches), 2)
        baseline_ids = {(m.get("baseline") or {}).get("baseline_id") for m in matches}
        self.assertEqual(baseline_ids, {"base_v1", "base_v2"})

    def test_find_rule_ref_missing(self):
        with self._patch():
            matches = baselines_svc.find_catalog_rules_by_ref(self.kv, "SV-999999")
        self.assertEqual(matches, [])

    def test_find_by_group_id(self):
        with self._patch():
            matches = baselines_svc.find_catalog_rules_by_group_id(self.kv, "V-000001")
        self.assertEqual(len(matches), 2)

    def test_find_by_cci_hit_and_empty(self):
        with self._patch():
            hits = baselines_svc.find_catalog_rules_by_cci(self.kv, "CCI-000366")
            empty = baselines_svc.find_catalog_rules_by_cci(self.kv, "CCI-999999")
        self.assertEqual(len(hits), 2)
        self.assertEqual(empty, [])

    def test_get_rule_by_key(self):
        with self._patch():
            row = baselines_svc.get_catalog_rule_reference(self.kv, "rule_a")
        self.assertEqual(row.get("rule_key"), "rule_a")
        self.assertEqual((row.get("baseline") or {}).get("baseline_id"), "base_v1")

    def test_stig_id_filter_skips_orphan_baseline_without_500(self):
        rule = self.rules[0]
        self.kv.tables["stig_baseline_rules"]["orphan"] = {
            "_key": "orphan",
            "baseline_id": "missing_baseline",
            "group_id": rule["group_id"],
            "rule_id": rule["rule_id"],
            "rule_id_src": "",
            "rule_version": rule["rule_version"],
            "severity": rule["severity"],
            "rule_title": "orphan",
            "group_title": "",
            "ccis": baselines_svc.dumps_json(rule.get("ccis") or []),
            "check_content_hash": rule["check_content_hash"],
        }
        with self._patch():
            filtered = baselines_svc.find_catalog_rules_by_ref(
                self.kv, "SV-000001", stig_id="Example_STIG"
            )
            all_matches = baselines_svc.find_catalog_rules_by_ref(self.kv, "SV-000001")
            cci_filtered = baselines_svc.find_catalog_rules_by_cci(
                self.kv, "CCI-000366", stig_id="Example_STIG"
            )
        self.assertEqual(len(filtered), 2)
        self.assertEqual(len(cci_filtered), 2)
        self.assertEqual(len(all_matches), 3)
        orphan_rows = [m for m in all_matches if m.get("rule_key") == "orphan"]
        self.assertEqual(len(orphan_rows), 1)
        self.assertFalse((orphan_rows[0].get("baseline") or {}).get("baseline_id"))

    def test_stig_id_filter_on_group_and_cci(self):
        with self._patch():
            by_group = baselines_svc.find_catalog_rules_by_group_id(
                self.kv, "V-000001", stig_id="Example_STIG"
            )
            by_group_miss = baselines_svc.find_catalog_rules_by_group_id(
                self.kv, "V-000001", stig_id="Other_STIG"
            )
        self.assertEqual(len(by_group), 2)
        self.assertEqual(by_group_miss, [])


class TestBaselineReferenceRest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kv = _RefKv()
        cls.meta, cls.rules = _load_fixture_rules()
        cls.kv.tables["stig_baselines"]["base_v1"] = {
            "_key": "base_v1",
            "stig_id": "Example_STIG",
            "version": "1",
            "title": "Example STIG v1",
        }
        rule = cls.rules[0]
        cls.kv.tables["stig_baseline_rules"]["rule_a"] = {
            "_key": "rule_a",
            "baseline_id": "base_v1",
            "group_id": rule["group_id"],
            "rule_id": rule["rule_id"],
            "rule_id_src": "",
            "rule_version": rule["rule_version"],
            "severity": rule["severity"],
            "rule_title": rule["rule_title"],
            "group_title": "",
            "ccis": baselines_svc.dumps_json(rule.get("ccis") or []),
            "check_content_hash": rule["check_content_hash"],
        }

    def _kv_patches(self):
        return patch.multiple(
            stig_rest_handler.baselines_svc.kv_client,
            get_collection=self.kv.get_collection,
            query_all=self.kv.query_all,
            get_by_key=self.kv.get_by_key,
        )

    def _dispatch(
        self,
        method: str,
        rest_path: str,
        session=None,
        query=None,
    ):
        handler = stig_rest_handler.StigRestHandler("", "")
        q = query or []
        if isinstance(q, dict):
            q = list(q.items())
        payload = {
            "method": method,
            "session": session
            or {"authtoken": "token", "user": "reader", "capabilities": {"stig_read": True}},
            "rest_path": rest_path,
            "query": q,
        }
        with patch.object(
            stig_rest_handler.kv_client, "connect", return_value=MagicMock()
        ), self._kv_patches():
            return handler.handle(json.dumps(payload))

    def test_get_rules_ref_200_and_404(self):
        resp = self._dispatch("GET", "stig_baselines/rules/SV-000001")
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertEqual(body["match_count"], 1)
        resp404 = self._dispatch("GET", "stig_baselines/rules/missing-rule")
        self.assertEqual(resp404["status"], 404)

    def test_get_cci_hit_and_empty(self):
        hit = self._dispatch("GET", "stig_baselines/ccis/CCI-000366")
        self.assertEqual(hit["status"], 200)
        self.assertEqual(json.loads(hit["payload"])["match_count"], 1)
        empty = self._dispatch("GET", "stig_baselines/ccis/CCI-999999")
        self.assertEqual(json.loads(empty["payload"])["match_count"], 0)

    def test_get_groups_hit_and_empty(self):
        hit = self._dispatch("GET", "stig_baselines/groups/V-000001")
        self.assertEqual(hit["status"], 200)
        self.assertEqual(json.loads(hit["payload"])["match_count"], 1)
        empty = self._dispatch("GET", "stig_baselines/groups/V-999999")
        self.assertEqual(json.loads(empty["payload"])["match_count"], 0)

    def test_get_rule_key_200_and_404(self):
        ok = self._dispatch("GET", "stig_baselines/rule/rule_a")
        self.assertEqual(ok["status"], 200)
        body = json.loads(ok["payload"])
        self.assertEqual(body.get("baseline_id"), "base_v1")
        self.assertEqual((body.get("rule") or {}).get("_key"), "rule_a")
        missing = self._dispatch("GET", "stig_baselines/rule/no-such-key")
        self.assertEqual(missing["status"], 404)

    def test_stig_id_query_on_rules_ref(self):
        resp = self._dispatch(
            "GET",
            "stig_baselines/rules/SV-000001",
            query={"stig_id": "Example_STIG"},
        )
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertEqual(body["stig_id"], "Example_STIG")
        self.assertEqual(body["match_count"], 1)

    def test_per_baseline_rules_route_not_shadowed(self):
        resp = self._dispatch("GET", "stig_baselines/base_v1/rules")
        self.assertEqual(resp["status"], 200)
        body = json.loads(resp["payload"])
        self.assertIsInstance(body, list)
        self.assertEqual(len(body), 1)

    def test_unauthenticated_401(self):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": "GET",
            "session": {},
            "rest_path": "stig_baselines/rules/SV-1",
            "query": [],
        }
        resp = handler.handle(json.dumps(payload))
        self.assertEqual(resp["status"], 401)


if __name__ == "__main__":
    unittest.main()
