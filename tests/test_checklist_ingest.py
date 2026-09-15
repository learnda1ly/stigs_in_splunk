import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers import ckl, cklb, ingest  # noqa: E402


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestChecklistIngest(unittest.TestCase):
    def test_detect_format(self):
        self.assertEqual(ingest.detect_format("host.ckl"), "ckl")
        self.assertEqual(ingest.detect_format("host.cklb"), "cklb")
        self.assertEqual(ingest.detect_format("", b'{"stigs":[]}'), "cklb")
        self.assertEqual(ingest.detect_format("", b"<CHECKLIST/>"), "ckl")

    def test_parse_ckl_ingest_watcher_shape(self):
        with open(os.path.join(FIXTURES, "minimal.ckl"), "rb") as handle:
            parsed = ckl.parse_ckl_ingest(handle.read(), source_uri="minimal.ckl")
        self.assertEqual(parsed["target"]["name"], "web-01")
        self.assertEqual(parsed["target"]["ip"], "10.0.0.8")
        self.assertEqual(len(parsed["checklists"]), 1)
        checklist = parsed["checklists"][0]
        self.assertEqual(checklist["benchmarkId"], "Example_STIG")
        self.assertEqual(checklist["revisionStr"], "V1R1")
        self.assertEqual(checklist["stats"]["fail"], 1)
        review = checklist["reviews"][0]
        self.assertEqual(review["ruleId"], "SV-000001r1_rule")
        self.assertEqual(review["result"], "fail")
        self.assertEqual(review["detail"], "sshd permits root login")
        self.assertEqual(review["comment"], "remediate next change window")
        self.assertEqual(review["groupId"], "V-000001")
        self.assertEqual(review["status"], "saved")
        self.assertIn("resultEngine", review)

    def test_parse_cklb_ingest_watcher_shape(self):
        with open(os.path.join(FIXTURES, "minimal.cklb"), "rb") as handle:
            parsed = cklb.parse_cklb_ingest(handle.read(), source_uri="minimal.cklb")
        self.assertEqual(parsed["target"]["name"], "db-01")
        self.assertFalse(parsed["target"]["noncomputing"])
        checklist = parsed["checklists"][0]
        self.assertEqual(checklist["benchmarkId"], "Example_STIG")
        self.assertEqual(checklist["stats"]["pass"], 1)
        review = checklist["reviews"][0]
        self.assertEqual(review["ruleId"], "SV-000001r1_rule")
        self.assertEqual(review["result"], "pass")
        self.assertEqual(review["detail"], "root login is disabled")
        self.assertEqual(review["groupId"], "V-000001")

    def test_cklb_falls_back_to_rule_id(self):
        doc = {
            "target_data": {"host_name": "h1"},
            "stigs": [
                {
                    "stig_id": "Example_STIG",
                    "version": "1",
                    "release_info": "Release: 2 Benchmark Date: 01 Jan 2026",
                    "rules": [
                        {
                            "group_id": "V-1",
                            "rule_id": "SV-1",
                            "status": "open",
                            "finding_details": "x",
                            "comments": "",
                        }
                    ],
                }
            ],
        }
        parsed = cklb.parse_cklb_ingest(json.dumps(doc), source_uri="fallback.cklb")
        review = parsed["checklists"][0]["reviews"][0]
        self.assertEqual(review["ruleId"], "SV-1")
        self.assertEqual(review["result"], "fail")

    def test_reviews_to_seeds(self):
        seeds = ingest.reviews_to_seeds(
            [
                {
                    "ruleId": "SV-000001r1_rule",
                    "groupId": "V-000001",
                    "result": "fail",
                    "detail": "bad",
                    "comment": "note",
                }
            ]
        )
        self.assertEqual(seeds["SV-000001r1_rule"]["status"], "open")
        self.assertEqual(seeds["SV-000001r1"]["finding_details"], "bad")
        self.assertEqual(seeds["V-000001"]["comments"], "note")
        matched = ingest.match_review_seed(
            {"rule_id": "SV-000001r1", "group_id": "V-000001"}, seeds
        )
        self.assertEqual(matched["status"], "open")

    def test_streamed_finding(self):
        review = ingest.streamed_review(
            rule_id="SV-1",
            result="pass",
            detail="ok",
            comment="",
            group_id="V-1",
        )
        finding = ingest.streamed_finding(
            review,
            asset_name="web-01",
            benchmark_id="Example_STIG",
            revision="V1R1",
            collection_id="abc",
            source_ref="minimal.ckl",
        )
        self.assertEqual(finding["assetName"], "web-01")
        self.assertEqual(finding["benchmarkId"], "Example_STIG")
        self.assertEqual(finding["ruleId"], "SV-1")
        self.assertEqual(finding["result"], "pass")
        self.assertEqual(finding["collectionId"], "abc")

    def test_fat_hec_event_can_rebuild_checklist(self):
        from importers.events import event_has_export_body, events_from_parsed, normalize_finding_event
        from models import is_ingest_locked

        with open(os.path.join(FIXTURES, "minimal.ckl"), "rb") as handle:
            parsed = ckl.parse_ckl_ingest(handle.read(), source_uri="minimal.ckl")
        events = events_from_parsed(parsed, "collection1", source_uri="minimal.ckl")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertTrue(event_has_export_body(event))
        self.assertEqual(event["assetName"], "web-01")
        self.assertEqual(event["asset"]["target_data"]["host_name"], "web-01")
        self.assertEqual(event["stig"]["stig_id"], "Example_STIG")
        self.assertEqual(event["rule"]["rule_title"], "Example rule title")
        self.assertTrue(event["rule"]["check_content"])
        self.assertEqual(event["result"], "fail")
        self.assertEqual(event["detail"], "sshd permits root login")
        normalized = normalize_finding_event(
            {
                "assetName": "web-01",
                "benchmarkId": "Example_STIG",
                "ruleId": "SV-1",
                "result": "pass",
                "detail": "ok",
                "comment": "",
            }
        )
        self.assertEqual(normalized["_status"], "not_a_finding")
        self.assertFalse(is_ingest_locked({"ingest_lock": False}))
        self.assertTrue(is_ingest_locked({"ingest_lock": True}))
        self.assertTrue(is_ingest_locked({"ingest_lock": "1"}))


if __name__ == "__main__":
    unittest.main()
