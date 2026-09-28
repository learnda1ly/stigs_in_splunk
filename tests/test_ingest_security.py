import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ingest_security import (  # noqa: E402
    hec_url_for_emit,
    validate_hec_url_admin,
    validate_ingest_index,
    validate_ingest_sourcetype,
    validate_reconcile_earliest,
)
from models import DEFAULT_HEC_URL  # noqa: E402


class TestIngestSecurity(unittest.TestCase):
    def test_hec_url_admin_allows_local_collector(self):
        url = "https://127.0.0.1:8088/services/collector/event"
        self.assertEqual(validate_hec_url_admin(url), url)

    def test_hec_url_admin_allows_off_host_https(self):
        url = "https://hec.example.com/services/collector/event"
        self.assertEqual(validate_hec_url_admin(url), url)

    def test_hec_url_admin_rejects_off_host_http(self):
        with self.assertRaises(ValueError):
            validate_hec_url_admin("http://hec.example.com/services/collector/event")

    def test_hec_url_admin_allows_loopback_http(self):
        url = "http://localhost:8088/services/collector/event"
        self.assertEqual(validate_hec_url_admin(url), url)

    def test_hec_url_for_emit_keeps_valid_off_host(self):
        url = "https://hec.example.com/services/collector/event"
        self.assertEqual(hec_url_for_emit(url), url)

    def test_hec_url_for_emit_falls_back_on_invalid(self):
        self.assertEqual(
            hec_url_for_emit("http://evil.example/services/collector/event"),
            DEFAULT_HEC_URL,
        )

    def test_ingest_index_rejects_spl(self):
        with self.assertRaises(ValueError):
            validate_ingest_index('stig | delete')

    def test_sourcetype_rejects_quotes(self):
        with self.assertRaises(ValueError):
            validate_ingest_sourcetype('stig:"finding"')

    def test_reconcile_earliest_allows_now(self):
        self.assertEqual(validate_reconcile_earliest("now"), "now")

    def test_reconcile_earliest_rejects_pipe(self):
        with self.assertRaises(ValueError):
            validate_reconcile_earliest("-15m | delete")


if __name__ == "__main__":
    unittest.main()
