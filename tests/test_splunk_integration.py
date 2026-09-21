"""End-to-end tests against the app custom REST API on a live Splunk instance."""

from __future__ import annotations

import json
import os
import unittest
import uuid

from splunk_client import SplunkRestError, require_splunk_client
from splunk_wait import wait_for_kv

FIXTURE_XCCDF = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")


class TestStigRestWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = require_splunk_client()
        try:
            wait_for_kv(cls.client)
        except TimeoutError as err:
            raise unittest.SkipTest(str(err)) from err
        cls.run_id = uuid.uuid4().hex[:8]
        cls.collection_id: str | None = None
        cls.host_id: str | None = None
        cls.baseline_id: str | None = None
        cls.checklist_id: str | None = None
        cls.review_id: str | None = None

        try:
            cls.client.get_app_json("stig_collections")
        except SplunkRestError as err:
            if err.status in (404, 502, 503):
                raise unittest.SkipTest(
                    "Custom REST not available; mount the app (scripts/link-splunk-app.sh) "
                    "and restart Splunk"
                ) from err
            if err.status == 403:
                raise unittest.SkipTest(
                    "Forbidden; grant stig_read/stig_write to your user "
                    "(see default/authorize.conf role_admin)"
                ) from err
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.checklist_id:
                cls.client.delete_app_json(f"stig_checklists/{cls.checklist_id}")
        except SplunkRestError:
            pass
        try:
            if cls.host_id:
                cls.client.delete_app_json(f"stig_hosts/{cls.host_id}")
        except SplunkRestError:
            pass
        try:
            if cls.collection_id:
                cls.client.delete_app_json(f"stig_collections/{cls.collection_id}")
        except SplunkRestError:
            pass

    def test_01_create_stig_collection(self):
        body = {
            "name": f"integration-{self.run_id}",
            "description": "Splunk integration test",
            "access_principals": [f"user:{self.client.username}"],
        }
        doc = self.client.post_app_json("stig_collections", body)
        self.assertIn("_key", doc)
        self.__class__.collection_id = doc["_key"]
        self.assertEqual(doc["name"], body["name"])

    def test_02_import_baseline_xccdf(self):
        self.assertTrue(self.collection_id, "collection missing")
        with open(FIXTURE_XCCDF, "rb") as handle:
            xml_bytes = handle.read()
        doc = self.client.post_app_raw(
            "stig_baselines/import",
            xml_bytes,
            content_type="application/xml",
            query={"format": "xccdf", "source_uri": "minimal_benchmark.xml"},
        )
        self.assertIn("_key", doc)
        self.__class__.baseline_id = doc["_key"]
        self.assertGreaterEqual(int(doc.get("rule_count") or 0), 1)

    def test_02b_import_baseline_deduplicated(self):
        self.assertTrue(self.baseline_id, "baseline missing from test_02")
        with open(FIXTURE_XCCDF, "rb") as handle:
            xml_bytes = handle.read()
        doc = self.client.post_app_raw(
            "stig_baselines/import",
            xml_bytes,
            content_type="application/xml",
            query={"format": "xccdf", "source_uri": "minimal_benchmark.xml"},
        )
        self.assertEqual(doc.get("_key"), self.baseline_id)
        self.assertTrue(doc.get("deduplicated"))

    def test_03_baseline_rules_list(self):
        self.assertTrue(self.baseline_id)
        rules = self.client.get_app_json(f"stig_baselines/{self.baseline_id}/rules")
        self.assertIsInstance(rules, list)
        self.assertGreaterEqual(len(rules), 1)
        self.assertEqual(rules[0].get("group_id"), "V-000001")

    def test_04_create_host(self):
        self.assertTrue(self.collection_id)
        body = {
            "stig_collection_id": self.collection_id,
            "hostname": f"host-{self.run_id}.example.com",
            "ip_address": "10.99.0.1",
        }
        doc = self.client.post_app_json("stig_hosts", body)
        self.__class__.host_id = doc["_key"]
        self.assertEqual(doc["hostname"], body["hostname"])

    def test_05_create_checklist_spawns_reviews(self):
        self.assertTrue(all([self.collection_id, self.host_id, self.baseline_id]))
        body = {
            "stig_collection_id": self.collection_id,
            "host_id": self.host_id,
            "baseline_id": self.baseline_id,
            "title": f"Checklist {self.run_id}",
        }
        doc = self.client.post_app_json("stig_checklists", body)
        self.__class__.checklist_id = doc["_key"]

        reviews = self.client.get_app_json(
            "stig_reviews", query={"checklist_id": self.checklist_id}
        )
        self.assertIsInstance(reviews, list)
        self.assertGreaterEqual(len(reviews), 1)
        self.__class__.review_id = reviews[0]["_key"]
        self.assertEqual(reviews[0].get("status"), "not_reviewed")
        self.assertFalse(reviews[0].get("valid"))

    def test_06_patch_review_and_export_cklb(self):
        self.assertTrue(self.review_id and self.checklist_id)
        updated = self.client.patch_app_json(
            f"stig_reviews/{self.review_id}",
            {
                "status": "open",
                "finding_details": "integration test finding",
                "comments": "automated test",
            },
        )
        self.assertEqual(updated.get("status"), "open")
        self.assertTrue(updated.get("valid"))

        raw = self.client.get_app_raw(
            f"stig_checklists/{self.checklist_id}/export",
            query={"format": "cklb"},
        )
        doc = json.loads(raw)
        rule = doc["stigs"][0]["rules"][0]
        self.assertEqual(rule["status"], "open")
        self.assertIn("integration test finding", rule.get("finding_details") or "")

    def test_07_batch_review_update(self):
        self.assertTrue(self.review_id and self.checklist_id)
        result = self.client.post_app_json(
            "stig_reviews/batch",
            {
                "reviews": [
                    {
                        "_key": self.review_id,
                        "status": "not_a_finding",
                        "finding_details": "batch path",
                        "comments": "integration batch",
                    }
                ],
            },
        )
        self.assertEqual(result.get("summary", {}).get("succeeded"), 1)
        self.assertEqual(result.get("summary", {}).get("failed"), 0)
        updated = (result.get("updated") or [])[0]
        self.assertEqual(updated.get("status"), "not_a_finding")
        self.assertTrue(updated.get("valid"))


if __name__ == "__main__":
    unittest.main()
