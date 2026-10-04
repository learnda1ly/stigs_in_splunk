"""Library import: optional replace of existing STIG revision (STE-50)."""

from __future__ import annotations

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
from models import check_content_hash  # noqa: E402
from services import baselines as baselines_svc  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows


class _ReplaceKv:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_baselines": {},
            "stig_baseline_rules": {},
        }
        self._seq = 0

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables[name])

    def query_all(
        self, coll: _MemColl, query: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query = query or {}
        return [
            dict(rec)
            for rec in coll._rows.values()
            if all(rec.get(k) == v for k, v in query.items())
        ]

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        rec = coll._rows.get(key)
        return dict(rec) if rec else None

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        self._seq += 1
        key = record.get("_key") or f"gen-{self._seq}"
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def batch_insert(self, coll: _MemColl, records: List[Dict[str, Any]]) -> None:
        for rec in records:
            self.insert_record(coll, rec)

    def update_record(
        self, coll: _MemColl, key: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        stored = dict(record)
        stored["_key"] = key
        coll._rows[key] = stored
        return stored

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll._rows.pop(key, None)


class TestBaselineImportReplace(unittest.TestCase):
    def setUp(self):
        self.kv = _ReplaceKv()
        self.service = MagicMock()
        self.patch_kv = patch("services.baselines.kv_client", self.kv)
        self.patch_audit = patch("services.baselines.audit.log_event")
        self.patch_kv.start()
        self.patch_audit.start()
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml"
        )
        with open(fixture, "rb") as handle:
            self.meta, self.rules = xccdf.parse_xccdf(handle.read())

    def tearDown(self):
        self.patch_audit.stop()
        self.patch_kv.stop()

    def test_default_keeps_fingerprint_match(self):
        first, created = baselines_svc.import_parsed_baseline(
            self.service, self.meta, self.rules, "alice"
        )
        self.assertTrue(created)
        second, created2 = baselines_svc.import_parsed_baseline(
            self.service, self.meta, self.rules, "alice"
        )
        self.assertFalse(created2)
        self.assertEqual(first["_key"], second["_key"])

    def test_replace_overwrites_fingerprint_match_in_place(self):
        first, _ = baselines_svc.import_parsed_baseline(
            self.service, self.meta, self.rules, "alice"
        )
        first_key = first["_key"]
        first_imported_at = first.get("imported_at")
        second, created = baselines_svc.import_parsed_baseline(
            self.service,
            self.meta,
            self.rules,
            "bob",
            replace_existing_revisions=True,
        )
        self.assertTrue(created)
        self.assertEqual(second["_key"], first_key)
        self.assertGreater(second.get("imported_at") or 0, first_imported_at or 0)
        self.assertEqual(second.get("imported_by"), "bob")

    def test_replace_overwrites_same_stig_id_and_version(self):
        first, _ = baselines_svc.import_parsed_baseline(
            self.service, self.meta, self.rules, "alice"
        )
        rules2 = [dict(self.rules[0])]
        rules2[0]["check_content"] = "Updated check text."
        rules2[0]["check_content_hash"] = check_content_hash(rules2[0]["check_content"])
        second, created = baselines_svc.import_parsed_baseline(
            self.service,
            self.meta,
            rules2,
            "alice",
            replace_existing_revisions=True,
        )
        self.assertTrue(created)
        self.assertEqual(second["_key"], first["_key"])
        self.assertNotEqual(
            second.get("content_fingerprint"), first.get("content_fingerprint")
        )
        stored_rules = baselines_svc.list_baseline_rules(self.service, first["_key"])
        self.assertEqual(len(stored_rules), 1)
        self.assertIn("Updated", stored_rules[0].get("check_content") or "")

    def test_without_replace_allows_duplicate_version_when_fingerprint_differs(self):
        first, _ = baselines_svc.import_parsed_baseline(
            self.service, self.meta, self.rules, "alice"
        )
        rules2 = [dict(self.rules[0])]
        rules2[0]["check_content"] = "Different check."
        rules2[0]["check_content_hash"] = check_content_hash(rules2[0]["check_content"])
        second, created = baselines_svc.import_parsed_baseline(
            self.service, self.meta, rules2, "alice"
        )
        self.assertTrue(created)
        self.assertNotEqual(second["_key"], first["_key"])


if __name__ == "__main__":
    unittest.main()
