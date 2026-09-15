import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import baselines as baselines_svc  # noqa: E402
from stig_ucc_kv import decode_uploaded_file, parse_principals, principals_to_text  # noqa: E402


class TestUccHelpers(unittest.TestCase):
    def test_decode_raw_xml(self):
        body = decode_uploaded_file("  <CHECKLIST></CHECKLIST>  ")
        self.assertEqual(body, b"<CHECKLIST></CHECKLIST>")

    def test_decode_zip_bytes_and_base64(self):
        import base64
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("U_Example_STIG_V1R1_Manual-xccdf.xml", b"<Benchmark/>")
        raw = buf.getvalue()
        self.assertTrue(raw.startswith(b"PK"))
        self.assertEqual(decode_uploaded_file(raw), raw)
        encoded = base64.b64encode(raw).decode("ascii")
        self.assertEqual(decode_uploaded_file(encoded), raw)

    def test_principals_roundtrip(self):
        self.assertEqual(parse_principals('["user:alice","role:stig_admin"]'), ["user:alice", "role:stig_admin"])
        self.assertIsNone(parse_principals(""))
        self.assertEqual(principals_to_text(["user:bob"]), '["user:bob"]')

    def test_ucc_name_fallback(self):
        self.assertEqual(baselines_svc.ucc_name_for({"ucc_name": "RHEL8", "_key": "abc"}), "RHEL8")
        self.assertEqual(baselines_svc.ucc_name_for({"_key": "abc"}), "abc")

    def test_normalize_roles_string_not_characters(self):
        from stig_ucc_kv import normalize_roles

        self.assertEqual(normalize_roles("admin"), ["admin"])
        self.assertEqual(normalize_roles("admin, stig_user"), ["admin", "stig_user"])
        self.assertEqual(normalize_roles(["admin", "power"]), ["admin", "power"])
        self.assertEqual(normalize_roles(""), [])


if __name__ == "__main__":
    unittest.main()
