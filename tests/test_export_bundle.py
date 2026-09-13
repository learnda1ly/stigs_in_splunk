import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from exporters import ckl  # noqa: E402
from services.checklists import export_filename  # noqa: E402


class TestExportBundle(unittest.TestCase):
    def test_filename_is_host_and_baseline(self):
        name = export_filename(
            {"_key": "ck1"},
            {"stig_id": "RHEL_8_STIG", "version": "V2R6"},
            {"hostname": "web-01.lab"},
            "cklb",
        )
        self.assertEqual(name, "web-01.lab_RHEL_8_STIG_V2R6.cklb")

    def test_ckl_uses_viewer_status_and_cci_ref(self):
        xml = ckl.export_ckl(
            {"title": "t", "target_data": "{}"},
            {"title": "STIG", "version": "1"},
            [{"group_id": "V-1", "rule_id": "SV-1_rule", "rule_title": "t", "ccis": ["CCI-000366"]}],
            {"V-1": {"status": "open", "package_id": "PKG-7", "finding_details": "x"}},
            {"hostname": "h1"},
        )
        self.assertIn("<STATUS>Open</STATUS>", xml)
        self.assertIn("CCI_REF", xml)
        self.assertIn("CCI-000366", xml)
        self.assertNotIn("Package_ID", xml)


if __name__ == "__main__":
    unittest.main()
