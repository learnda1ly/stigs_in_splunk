"""Result engine persistence, API annotation, and XCCDF export."""

import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from exporters import xccdf_results as xccdf_export  # noqa: E402
from importers.ingest import review_seed_payload  # noqa: E402
from models import result_engine_origin  # noqa: E402
from validation import annotate_review  # noqa: E402


class TestResultEngineOrigin(unittest.TestCase):
    def test_manual_when_empty(self):
        self.assertEqual(result_engine_origin(None), "manual")
        self.assertEqual(result_engine_origin(""), "manual")

    def test_automated_with_product(self):
        engine = {"type": "script", "product": "Evaluate-STIG", "version": "1.0"}
        self.assertEqual(result_engine_origin(engine), "automated")

    def test_override_when_overrides_present(self):
        engine = {
            "product": "Evaluate-STIG",
            "overrides": [{"authority": "admin", "oldResult": "fail", "newResult": "pass"}],
        }
        self.assertEqual(result_engine_origin(engine), "override")

    def test_annotate_review_exposes_origin(self):
        annotated = annotate_review(
            {
                "status": "open",
                "result_engine": '{"product":"Evaluate-STIG","type":"script"}',
            }
        )
        self.assertEqual(annotated["result_engine_origin"], "automated")


class TestResultEngineExport(unittest.TestCase):
    def test_xccdf_export_includes_check_system_and_override_message(self):
        xml = xccdf_export.export_xccdf_results(
            {"_key": "cl1", "title": "host"},
            {
                "stig_id": "Example_STIG",
                "xccdf_benchmark_id": "xccdf_mil.disa.stig_benchmark_Example_STIG",
            },
            [
                {
                    "rule_id": "SV-000001",
                    "group_id": "V-000001",
                    "rule_id_src": "xccdf_mil.disa.stig_rule_SV-000001",
                }
            ],
            [
                {
                    "status": "open",
                    "finding_details": "bad",
                    "rule_id": "SV-000001",
                    "group_id": "V-000001",
                    "result_engine": {
                        "type": "script",
                        "product": "Evaluate-STIG",
                        "version": "1.2.3",
                        "overrides": [
                            {
                                "authority": "assessor",
                                "oldResult": "fail",
                                "newResult": "pass",
                                "remark": "approved exception",
                            }
                        ],
                    },
                }
            ],
            {"hostname": "host01"},
        )
        root = ET.fromstring(xml)
        ns = {"x": "http://checklists.nist.gov/xccdf/1.2"}
        rr = root.find("x:rule-result", ns)
        self.assertIsNotNone(rr)
        check = rr.find("x:check", ns)
        self.assertIsNotNone(check)
        self.assertEqual(check.get("system"), "Evaluate-STIG")
        messages = rr.findall("x:message", ns)
        bodies = [m.text or "" for m in messages]
        self.assertTrue(any("Overridden by" in text for text in bodies))


class TestResultEngineReviewUpdate(unittest.TestCase):
    def test_status_change_clears_result_engine_without_explicit_body(self):
        from services import reviews as reviews_svc  # noqa: E402

        existing = {
            "_key": "rev-1",
            "checklist_id": "cl-1",
            "status": "open",
            "result_engine": '{"product":"Evaluate-STIG"}',
            "finding_details": "x",
            "comments": "",
        }
        coll = MagicMock()
        with patch.object(reviews_svc.kv_client, "get_collection", return_value=coll):
            with patch.object(reviews_svc.kv_client, "get_by_key", return_value=existing):
                with patch.object(
                    reviews_svc.kv_client, "update_record", side_effect=lambda _c, _k, rec: rec
                ):
                    with patch.object(
                        reviews_svc.checklists_svc,
                        "get_checklist",
                        return_value={"stig_collection_id": "ws-1"},
                    ):
                        with patch.object(
                            reviews_svc,
                            "_workspace_for_checklist",
                            return_value=("ws-1", {}),
                        ):
                            with patch.object(reviews_svc.access, "user_can_write_collection", return_value=True):
                                with patch.object(reviews_svc.review_history_svc, "record_review_change"):
                                    with patch.object(reviews_svc.audit, "log_event"):
                                        updated = reviews_svc.update_review(
                                            MagicMock(),
                                            "rev-1",
                                            {"status": "not_a_finding"},
                                            "alice",
                                            {"capabilities": {"stig_write": True}},
                                        )
        self.assertEqual(updated.get("result_engine"), "")


if __name__ == "__main__":
    unittest.main()
