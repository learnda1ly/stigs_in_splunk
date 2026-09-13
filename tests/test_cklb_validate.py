import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cklb_validate import validate_cklb_doc, validate_cklb_file  # noqa: E402
from exporters import cklb  # noqa: E402
from importers import xccdf  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SV_CKLB = Path("/home/squinlan/New Checklist.cklb")
APP_CKLB = Path("/home/squinlan/web-01_STIG_2.cklb")


def _minimal_export() -> dict:
    fixture = REPO / "tests" / "fixtures" / "minimal_benchmark.xml"
    meta, rules = xccdf.parse_xccdf(fixture.read_bytes())
    return json.loads(
        cklb.export_cklb(
            {"_key": "ck1", "title": "Test"},
            {"_key": "b1", **meta},
            rules,
            [{"group_id": "V-000001", "status": "open", "finding_details": "x", "comments": ""}],
            {"hostname": "h1"},
        )
    )


class TestCklbValidate(unittest.TestCase):
    def test_exporter_output_has_viewer_shape(self):
        result = validate_cklb_doc(_minimal_export(), path="minimal.cklb")
        self.assertTrue(result.ok, "\n".join(result.errors))
        self.assertEqual(result.rule_count, 1)

    def test_thin_document_fails(self):
        thin = {
            "title": "x",
            "id": "not-a-uuid",
            "cklb_version": "1.0",
            "active": False,
            "mode": 1,
            "has_path": True,
            "target_data": {"host_name": "h"},
            "stigs": [{"stig_id": "STIG", "rules": [{"rule_id": "SV-1_rule", "group_id": ""}]}],
        }
        result = validate_cklb_doc(thin, path="thin.cklb")
        self.assertFalse(result.ok)
        blob = " ".join(result.errors)
        self.assertIn("mode", blob)
        self.assertIn("group_id", blob)

    @unittest.skipUnless(SV_CKLB.is_file(), "STIG Viewer CKLB not present")
    def test_stig_viewer_file_passes(self):
        result = validate_cklb_file(SV_CKLB)
        self.assertTrue(result.ok, "\n".join(result.errors[:8]))
        self.assertEqual(result.rule_count, 366)

    @unittest.skipUnless(APP_CKLB.is_file(), "old app CKLB not present")
    def test_old_app_export_fails_shape(self):
        result = validate_cklb_file(APP_CKLB)
        self.assertFalse(result.ok)

    def test_cli_accepts_valid_file(self):
        doc = _minimal_export()
        path = REPO / "tests" / "fixtures" / "_tmp_valid.cklb"
        try:
            path.write_text(json.dumps(doc))
            proc = subprocess.run(
                [sys.executable, str(REPO / "scripts" / "validate_cklb.py"), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("OK", proc.stdout)
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
