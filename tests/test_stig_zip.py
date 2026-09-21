import io
import os
import sys
import unittest
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.stig_zip import is_baseline_xccdf_name, list_baseline_xccdfs  # noqa: E402
from services.baselines import suggested_ucc_name  # noqa: E402


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "minimal_benchmark.xml")


def _zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buf.getvalue()


class TestStigZip(unittest.TestCase):
    def test_name_filter(self):
        self.assertTrue(
            is_baseline_xccdf_name("U_RHEL_8_STIG_V2R6_Manual-xccdf.xml")
        )
        self.assertFalse(
            is_baseline_xccdf_name("U_General_Purpose_Operating_System_SRG_V2R6_Manual-xccdf.xml")
        )
        self.assertFalse(is_baseline_xccdf_name("U_RHEL_8_STIG_SCAP_1-2_Benchmark.xml"))
        self.assertFalse(is_baseline_xccdf_name("host.ckl"))

    def test_nested_zip_extracts_manual_xccdf_only(self):
        with open(FIXTURE, "rb") as handle:
            xccdf = handle.read()
        inner = _zip_bytes(
            [
                ("U_Example_STIG_V1R1_Manual-xccdf.xml", xccdf),
                ("U_Example_SRG_V1R1_Manual-xccdf.xml", b"<Benchmark/>"),
                ("readme.pdf", b"%PDF"),
            ]
        )
        outer = _zip_bytes(
            [
                ("U_STIG_Library.zip", inner),
                ("notes.txt", b"ignore"),
            ]
        )
        found = list_baseline_xccdfs(outer)
        self.assertEqual(len(found), 1)
        self.assertIn("Manual-xccdf.xml", found[0][0])
        self.assertEqual(found[0][1], xccdf)

    def test_empty_zip_errors(self):
        with self.assertRaises(ValueError):
            list_baseline_xccdfs(_zip_bytes([("readme.txt", b"hi")]))

    def test_suggested_ucc_name(self):
        used = set()
        first = suggested_ucc_name({"stig_id": "RHEL_8_STIG", "version": "2.6"}, used)
        second = suggested_ucc_name({"stig_id": "RHEL_8_STIG", "version": "2.6"}, used)
        self.assertEqual(first, "RHEL_8_STIG_2.6")
        self.assertEqual(second, "RHEL_8_STIG_2.6_2")


if __name__ == "__main__":
    unittest.main()
