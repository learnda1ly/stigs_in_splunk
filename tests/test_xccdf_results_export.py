"""XCCDF TestResult export from KV checklists (collection archive and single export)."""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List
from unittest.mock import patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from importers import xccdf_results as xccdf_results_import  # noqa: E402
from models import strip_ns  # noqa: E402
from services import checklists as checklists_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _MemKv:
    def __init__(self):
        self.checklists: Dict[str, Dict[str, Any]] = {}
        self.reviews: Dict[str, Dict[str, Any]] = {}

    def get_collection(self, _service, name: str) -> _MemColl:
        if name == "stig_checklists":
            return _MemColl(self.checklists)
        if name == "stig_reviews":
            return _MemColl(self.reviews)
        raise KeyError(name)

    def query_all(self, coll: _MemColl, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        query = query or {}
        out = []
        for rec in coll._rows.values():
            ok = True
            for key, val in query.items():
                if rec.get(key) != val:
                    ok = False
                    break
            if ok:
                out.append(dict(rec))
        return out

    def get_by_key(self, coll: _MemColl, key: str) -> Dict[str, Any] | None:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None


def _wire_kv_patches(kv: _MemKv):
    return (
        patch("services.checklists.kv_client.get_collection", side_effect=kv.get_collection),
        patch("services.checklists.kv_client.query_all", side_effect=kv.query_all),
        patch("services.checklists.kv_client.get_by_key", side_effect=kv.get_by_key),
    )


class TestXccdfResultsExport(unittest.TestCase):
    def setUp(self):
        self.service = object()
        self.session = {
            "user": "alice",
            "roles": [],
            "capabilities": {"stig_read": True, "stig_write": True},
        }
        self.ws = {
            "_key": "ws1",
            "name": "Lab Workspace",
            "access_principals": '["user:alice"]',
        }
        self.host = {
            "_key": "host_a",
            "stig_collection_id": "ws1",
            "hostname": "web-01.lab",
        }
        self.baseline = {
            "_key": "base1",
            "stig_id": "RHEL_8_STIG",
            "title": "RHEL 8 STIG",
            "version": "V2R6",
            "xccdf_benchmark_id": "xccdf_mil.disa.stig_benchmark_RHEL_8_STIG",
        }
        self.rules = [
            {
                "group_id": "V-1",
                "rule_id": "SV-1",
                "rule_id_src": "xccdf_mil.disa.stig_rule_SV-1",
                "rule_title": "Rule one",
            },
            {
                "group_id": "V-2",
                "rule_id": "SV-2",
                "rule_id_src": "xccdf_mil.disa.stig_rule_SV-2",
                "rule_title": "Rule two",
            },
        ]
        self.kv = _MemKv()
        self.kv.checklists = {
            "cl1": {
                "_key": "cl1",
                "stig_collection_id": "ws1",
                "host_id": "host_a",
                "baseline_id": "base1",
                "title": "t1",
                "target_data": "{}",
                "updated_at": 1704067200.0,
            }
        }
        self.kv.reviews = {
            "rv1": {
                "_key": "rv1",
                "checklist_id": "cl1",
                "group_id": "V-1",
                "rule_id": "SV-1",
                "status": "open",
                "finding_details": "failed check",
            },
            "rv2": {
                "_key": "rv2",
                "checklist_id": "cl1",
                "group_id": "V-2",
                "rule_id": "SV-2",
                "status": "not_a_finding",
                "finding_details": "",
            },
        }

    @patch("services.checklists.baselines_svc.list_baseline_rules")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    def test_single_export_xml_structure_and_round_trip(
        self,
        get_coll,
        _grants,
        mock_get_host,
        mock_get_baseline,
        mock_rules,
    ):
        get_coll.return_value = self.ws
        mock_get_baseline.return_value = self.baseline
        mock_rules.return_value = self.rules
        mock_get_host.return_value = self.host

        patches = _wire_kv_patches(self.kv)
        for p in patches:
            p.start()
        try:
            xml_text = checklists_svc.export_checklist(
                self.service, "cl1", "xccdf", self.session
            )
            _, filename = checklists_svc.export_checklist_file(
                self.service, "cl1", "xccdf", self.session
            )
        finally:
            for p in patches:
                p.stop()

        self.assertEqual(filename, "web-01.lab_RHEL_8_STIG_V2R6-results.xml")
        root = ET.fromstring(xml_text)
        self.assertEqual(strip_ns(root.tag), "TestResult")
        self.assertEqual(root.findtext("{*}target"), "web-01.lab")
        rule_results = root.findall("{*}rule-result")
        self.assertEqual(len(rule_results), 2)
        by_idref = {rr.get("idref"): rr.get("result") for rr in rule_results}
        self.assertEqual(by_idref["xccdf_mil.disa.stig_rule_SV-1"], "fail")
        self.assertEqual(by_idref["xccdf_mil.disa.stig_rule_SV-2"], "pass")

        parsed = xccdf_results_import.parse_xccdf_results(
            xml_text.encode("utf-8"), source_uri=filename
        )
        self.assertEqual(parsed["target"]["name"], "web-01.lab")
        checklist = parsed["checklists"][0]
        self.assertEqual(checklist["benchmarkId"], "RHEL_8_STIG")
        self.assertEqual(checklist["stats"]["fail"], 1)
        self.assertEqual(checklist["stats"]["pass"], 1)

    @patch("services.checklists.baselines_svc.list_baseline_rules")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.hosts_svc.get_host")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    def test_collection_archive_xccdf_zip(
        self,
        get_coll,
        _grants,
        mock_get_host,
        mock_get_baseline,
        mock_rules,
    ):
        get_coll.return_value = self.ws
        mock_get_baseline.return_value = self.baseline
        mock_rules.return_value = self.rules
        mock_get_host.return_value = self.host

        patches = _wire_kv_patches(self.kv)
        for p in patches:
            p.start()
        try:
            result = checklists_svc.export_collection_archive(
                self.service, "ws1", "xccdf", self.session
            )
        finally:
            for p in patches:
                p.stop()

        self.assertEqual(result["format"], "xccdf")
        self.assertEqual(result["filename"], "stig-archive-Lab_Workspace-xccdf.zip")
        self.assertEqual(result["files"], ["web-01.lab_RHEL_8_STIG_V2R6-results.xml"])
        raw = base64.b64decode(result["content_base64"])
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            names = archive.namelist()
            self.assertEqual(names, result["files"])
            body = archive.read(names[0]).decode("utf-8")
        self.assertIn("TestResult", body)
        self.assertIn("rule-result", body)


if __name__ == "__main__":
    unittest.main()
