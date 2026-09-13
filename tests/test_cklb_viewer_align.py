import json
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cklb_shape import (  # noqa: E402
    derive_group_id,
    parse_disa_description,
    resolve_stig_id,
    viewer_rule_ids,
)
from exporters import cklb  # noqa: E402
from importers import xccdf  # noqa: E402

APP_CKLB = Path("/home/squinlan/web-01_STIG_2.cklb")
SV_CKLB = Path("/home/squinlan/New Checklist.cklb")
VIEWER_RULE_KEYS = [
    "group_id_src",
    "group_tree",
    "group_id",
    "severity",
    "group_title",
    "rule_id_src",
    "rule_id",
    "rule_version",
    "rule_title",
    "fix_text",
    "weight",
    "check_content",
    "check_content_ref",
    "classification",
    "discussion",
    "false_positives",
    "false_negatives",
    "documentable",
    "security_override_guidance",
    "potential_impacts",
    "third_party_tools",
    "ia_controls",
    "responsibility",
    "mitigations",
    "mitigation_control",
    "legacy_ids",
    "ccis",
    "reference_identifier",
    "uuid",
    "stig_uuid",
    "status",
    "overrides",
    "comments",
    "finding_details",
    "srg_id",
]


class TestCklbViewerAlign(unittest.TestCase):
    def test_stig_id_from_xccdf_11_benchmark(self):
        self.assertEqual(resolve_stig_id({"xccdf_benchmark_id": "RHEL_8_STIG", "stig_id": "STIG"}), "RHEL_8_STIG")
        self.assertEqual(
            resolve_stig_id({"xccdf_benchmark_id": "xccdf_mil.disa.stig_benchmark_Example_STIG"}),
            "Example_STIG",
        )

    def test_rule_id_and_group_id_from_viewer_forms(self):
        rule = {"rule_id": "SV-230221r1017040_rule", "rule_id_src": "SV-230221r1017040_rule", "group_id": ""}
        src, rid = viewer_rule_ids(rule)
        self.assertEqual(src, "SV-230221r1017040_rule")
        self.assertEqual(rid, "SV-230221r1017040")
        self.assertEqual(derive_group_id(rule), "V-230221")

    def test_disa_description_strips_wrapper(self):
        raw = (
            "<VulnDiscussion>Keep this text.</VulnDiscussion>"
            "<FalsePositives></FalsePositives><Documentable>false</Documentable>"
        )
        parsed = parse_disa_description(raw)
        self.assertEqual(parsed["discussion"], "Keep this text.")
        self.assertEqual(parsed["documentable"], "false")

    @unittest.skipUnless(APP_CKLB.is_file() and SV_CKLB.is_file(), "home CKLB files not present")
    def test_reexport_matches_viewer_shape_and_content(self):
        import zipfile

        cache = Path(__file__).resolve().parents[1] / "tests/fixtures/cache/U_RHEL_8_V2R6_STIG.zip"
        if not cache.is_file():
            self.skipTest("RHEL 8 XCCDF zip is not cached")
        with zipfile.ZipFile(cache) as zf:
            member = next(n for n in zf.namelist() if n.endswith("Manual-xccdf.xml"))
            meta, rules = xccdf.parse_xccdf(zf.read(member), source_uri=member)
        app = json.loads(APP_CKLB.read_text())
        viewer = json.loads(SV_CKLB.read_text())
        baseline = {
            "_key": "baseline-rhel8",
            **meta,
        }
        checklist = {
            "_key": app["id"],
            "title": app["title"],
            "target_data": json.dumps(app["target_data"]),
        }
        host = {"hostname": "web-01", "ip_address": "10.0.0.10", "fqdn": "web-01.example.com"}
        out = json.loads(cklb.export_cklb(checklist, baseline, rules, [], host))
        self.assertEqual(list(out.keys()), list(viewer.keys()))
        self.assertEqual(list(out["target_data"].keys()), list(viewer["target_data"].keys()))
        self.assertEqual(list(out["stigs"][0].keys()), list(viewer["stigs"][0].keys()))
        self.assertEqual(out["stigs"][0]["stig_id"], "RHEL_8_STIG")
        self.assertEqual(out["stigs"][0]["display_name"], "Red Hat Enterprise Linux 8")
        self.assertEqual(out["mode"], 2)
        self.assertTrue(out["active"])
        self.assertFalse(out["has_path"])

        by_ver_out = {r["rule_version"]: r for r in out["stigs"][0]["rules"]}
        by_ver_sv = {r["rule_version"]: r for r in viewer["stigs"][0]["rules"]}
        self.assertEqual(set(by_ver_out), set(by_ver_sv))
        sample = by_ver_sv["RHEL-08-010000"]
        got = by_ver_out["RHEL-08-010000"]
        for key in VIEWER_RULE_KEYS:
            self.assertIn(key, got)
        self.assertEqual(list(got.keys())[: len(VIEWER_RULE_KEYS)], VIEWER_RULE_KEYS)
        self.assertEqual(got["group_id"], sample["group_id"])
        self.assertEqual(got["rule_id"], sample["rule_id"])
        self.assertEqual(got["rule_id_src"], sample["rule_id_src"])
        self.assertEqual(got["srg_id"], sample["srg_id"])
        self.assertEqual(got["discussion"], sample["discussion"])
        self.assertEqual(got["check_content_ref"], sample["check_content_ref"])
        mismatches = []
        ignore = {"status", "uuid", "stig_uuid", "package_id", "overrides"}
        for ver, sv_rule in by_ver_sv.items():
            ours = by_ver_out[ver]
            for key in VIEWER_RULE_KEYS:
                if key in ignore:
                    continue
                if ours.get(key) != sv_rule.get(key):
                    mismatches.append((ver, key))
        # reference_identifier is absent on the already-imported baseline
        mismatches = [m for m in mismatches if m[1] != "reference_identifier"]
        self.assertEqual(mismatches[:10], [], msg=f"{len(mismatches)} field mismatches")


class TestXccdfRhelIds(unittest.TestCase):
    def test_minimal_fixture_still_parses(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")
        with open(fixture, "rb") as handle:
            meta, rules = xccdf.parse_xccdf(handle.read())
        self.assertEqual(meta["stig_id"], "Example_STIG")
        self.assertEqual(rules[0]["group_id"], "V-000001")
        self.assertEqual(rules[0]["rule_id"], "SV-000001")


if __name__ == "__main__":
    unittest.main()
