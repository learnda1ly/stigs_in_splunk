import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ingest_security import (  # noqa: E402
    normalize_hec_url,
    validate_hec_url,
    validate_ingest_index,
    validate_ingest_sourcetype,
    validate_reconcile_earliest,
)
from models import DEFAULT_HEC_URL  # noqa: E402


class TestIngestSecurity(unittest.TestCase):
    def test_hec_url_allows_local_collector(self):
        url = "https://127.0.0.1:8088/services/collector/event"
        self.assertEqual(validate_hec_url(url), url)

    def test_hec_url_rejects_external_host(self):
        with self.assertRaises(ValueError):
            validate_hec_url("https://evil.example/services/collector/event")

    def test_normalize_hec_url_falls_back(self):
        self.assertEqual(
            normalize_hec_url("https://evil.example/services/collector/event"),
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
