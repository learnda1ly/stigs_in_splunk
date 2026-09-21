"""Integration tests: Splunk KV store collections for the app."""

from __future__ import annotations

import os
import unittest
import uuid

from splunk_client import SplunkRestError, require_splunk_client
from splunk_wait import retry_on_503, wait_for_kv

def _extract_kv_key(raw) -> str | None:
    if isinstance(raw, dict):
        if raw.get("_key"):
            return raw["_key"]
        entries = raw.get("entry") or []
        if entries:
            entry = entries[0]
            if entry.get("name"):
                return entry["name"]
            content = entry.get("content") or {}
            if content.get("_key"):
                return content["_key"]
    return None


COLLECTIONS = (
    "stig_collections",
    "stig_hosts",
    "stig_baselines",
    "stig_baseline_rules",
    "stig_checklists",
    "stig_reviews",
    "stig_editor_settings",
    "stig_assignment_rules",
    "stig_host_baseline_assignments",
)


class TestSplunkKvStoreCollections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.client = require_splunk_client()
            wait_for_kv(cls.client)
        except unittest.SkipTest:
            raise
        except TimeoutError as err:
            raise unittest.SkipTest(str(err)) from err
        try:
            cls.client.get_json(
                cls.client.app_path("storage/collections/config/stig_collections")
            )
        except SplunkRestError as err:
            if err.status in (404, 503):
                raise unittest.SkipTest(
                    "stigs_in_splunk app or KV collections not loaded; "
                    "symlink the app into $SPLUNK_HOME/etc/apps and reload collections"
                ) from err
            raise

    def test_all_collection_stanzas_exist(self):
        for name in COLLECTIONS:
            with self.subTest(collection=name):
                doc = self.client.get_json(
                    self.client.app_path(f"storage/collections/config/{name}")
                )
                if isinstance(doc, dict) and doc.get("entry"):
                    stanza_name = doc["entry"][0].get("name")
                    content = doc["entry"][0].get("content") or {}
                else:
                    stanza_name = name
                    content = doc if isinstance(doc, dict) else {}
                self.assertEqual(stanza_name, name)
                self.assertEqual(str(content.get("enforcetypes", "true")).lower(), "true")


class TestSplunkKvStoreCrud(unittest.TestCase):
    """Direct KV write/read (validates collections.conf field types)."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.client = require_splunk_client()
            cls.client.get_json(
                cls.client.app_path("storage/collections/config/stig_collections")
            )
        except (unittest.SkipTest, SplunkRestError) as err:
            raise unittest.SkipTest(f"KV store unavailable: {err}") from err

    def setUp(self):
        self.collection_id = str(uuid.uuid4())
        self._key: str | None = None

    def tearDown(self):
        if not self._key:
            return
        path = self.client.app_path(
            f"storage/collections/data/stig_collections/{self._key}"
        )
        try:
            self.client.delete_json(path)
        except SplunkRestError:
            pass

    def test_insert_and_query_stig_collection_row(self):
        import json
        import time

        row = {
            "name": f"kvtest-{self.collection_id[:8]}",
            "description": "integration test",
            "access_principals": json.dumps(["user:admin"]),
            "created_at": time.time(),
            "updated_at": time.time(),
            "created_by": "integration-test",
            "updated_by": "integration-test",
        }
        insert_path = self.client.app_path("storage/collections/data/stig_collections")
        def _insert():
            return self.client.request("POST", insert_path, body=row)

        _, raw = retry_on_503(_insert)
        self._key = _extract_kv_key(raw)
        self.assertTrue(self._key, f"unexpected insert response: {raw!r}")

        fetched = self.client.get_json(
            self.client.app_path(f"storage/collections/data/stig_collections/{self._key}")
        )
        if isinstance(fetched, dict) and "entry" in fetched:
            content = fetched["entry"][0]["content"]
        else:
            content = fetched
        self.assertEqual(content.get("name"), row["name"])
