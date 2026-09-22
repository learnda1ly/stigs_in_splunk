import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import hec as hec_svc  # noqa: E402
from services import settings as settings_svc  # noqa: E402

# Catalog in globalConfig.yaml (general tab) + spec §4.3.1 — not hec_token.
DOCUMENTED_SETTING_FIELDS = frozenset(
    {
        "vim_mode",
        "trust_event_collection_id",
        "ingest_index",
        "ingest_sourcetype",
        "hec_url",
        "reconcile_earliest",
    }
)


class TestSettingsNeverExposeHecToken(unittest.TestCase):
    def test_public_payload_matches_documented_catalog(self):
        rec = {
            "vim_mode": True,
            "trust_event_collection_id": False,
            "ingest_index": "stig",
            "ingest_sourcetype": "stig:finding",
            "hec_url": "https://localhost:8088/services/collector/event",
            "reconcile_earliest": "-15m",
        }
        public = settings_svc._public(rec, "admin")
        for key in DOCUMENTED_SETTING_FIELDS:
            self.assertIn(key, public)
        self.assertNotIn("hec_token", public)

    def test_public_payload_strips_token(self):
        rec = {
            "_key": "settings",
            "vim_mode": True,
            "ingest_index": "stig",
            "ingest_sourcetype": "stig:finding",
            "hec_url": "https://localhost:8088/services/collector/event",
            "hec_token": "super-secret-token",
            "reconcile_earliest": "-15m",
        }
        public = settings_svc._public(rec)
        self.assertNotIn("hec_token", public)
        self.assertNotIn("hec_token_set", public)
        dumped = str(public)
        self.assertNotIn("super-secret-token", dumped)

    def test_save_ignores_incoming_token(self):
        stored = {}

        class _Coll:
            pass

        def _query_all(_coll):
            return []

        def _insert(_coll, record):
            stored.update(record)
            stored["_key"] = "k1"
            return dict(stored)

        orig_get = settings_svc.kv_client.get_collection
        orig_query = settings_svc.kv_client.query_all
        orig_insert = settings_svc.kv_client.insert_record
        settings_svc.kv_client.get_collection = lambda _svc, _name: _Coll()
        settings_svc.kv_client.query_all = _query_all
        settings_svc.kv_client.insert_record = _insert
        try:
            out = settings_svc.save_settings(
                object(),
                {"vim_mode": False, "hec_token": "should-not-persist"},
                "admin",
            )
        finally:
            settings_svc.kv_client.get_collection = orig_get
            settings_svc.kv_client.query_all = orig_query
            settings_svc.kv_client.insert_record = orig_insert
        self.assertNotIn("hec_token", stored)
        self.assertNotIn("hec_token", out)
        self.assertNotIn("should-not-persist", str(stored) + str(out))


class TestHecTokenLookup(unittest.TestCase):
    def test_parse_inputs_conf_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "inputs.conf")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("[http]\ndisabled = 0\n\n")
                handle.write("[http://stig_findings]\n")
                handle.write("disabled = 0\n")
                handle.write('token = "abc-123-secret"\n')
                handle.write("index = stig\n")
            token = hec_svc._parse_stanza_token(path, hec_svc.HEC_STANZA)
            self.assertEqual(token, "abc-123-secret")

    def test_emit_findings_result_has_no_token(self):
        posted = {}

        def _fake_post(url, token, events, index, sourcetype, source):
            posted["token"] = token
            posted["url"] = url
            return len(events)

        orig = hec_svc._post_hec
        orig_lookup = hec_svc.lookup_hec_token
        hec_svc._post_hec = _fake_post
        hec_svc.lookup_hec_token = lambda session_key="": "server-only-token"
        try:
            result = hec_svc.emit_findings(
                [{"ruleId": "SV-1", "result": "pass"}],
                settings={"hec_url": "https://hec.example/event"},
                session_key="sess",
            )
        finally:
            hec_svc._post_hec = orig
            hec_svc.lookup_hec_token = orig_lookup
        self.assertEqual(result["via"], "hec")
        self.assertEqual(result["indexed"], 1)
        self.assertNotIn("token", result)
        self.assertNotIn("hec_token", result)
        self.assertNotIn("server-only-token", str(result))
        self.assertEqual(posted["token"], "server-only-token")


if __name__ == "__main__":
    unittest.main()
