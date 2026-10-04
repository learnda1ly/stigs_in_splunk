"""Web/database asset identity matching on ingest (STIG Manager §2.10)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services import apply as apply_svc  # noqa: E402
from services import hosts as hosts_svc  # noqa: E402


def _web_event(hostname: str, site: str, instance: str) -> dict:
    return {
        "assetName": hostname,
        "benchmarkId": "RHEL_8_STIG",
        "asset": {
            "name": hostname,
            "metadata": {
                "cklWebOrDatabase": "true",
                "cklHostName": hostname,
                "cklWebDbSite": site,
                "cklWebDbInstance": instance,
            },
            "target_data": {
                "is_web_database": True,
                "host_name": hostname,
                "web_db_site": site,
                "web_db_instance": instance,
            },
        },
    }


def _plain_event(hostname: str) -> dict:
    return {
        "assetName": hostname,
        "benchmarkId": "RHEL_8_STIG",
        "asset": {"name": hostname, "metadata": {}, "target_data": {}},
    }


class WebDbHostMatchTests(unittest.TestCase):
    def test_plain_host_matches_hostname_only(self):
        host = {"hostname": "app01", "web_or_database": False, "metadata": "{}"}
        self.assertTrue(hosts_svc.host_matches_ingest(host, _plain_event("app01")))
        self.assertFalse(hosts_svc.host_matches_ingest(host, _plain_event("app02")))

    def test_web_hosts_same_hostname_different_site(self):
        host_a = {
            "hostname": "sql01",
            "web_or_database": True,
            "metadata": (
                '{"cklWebOrDatabase":"true","cklHostName":"sql01",'
                '"cklWebDbSite":"cluster-a","cklWebDbInstance":"MSSQL"}'
            ),
        }
        host_b = {
            "hostname": "sql01",
            "web_or_database": True,
            "metadata": (
                '{"cklWebOrDatabase":"true","cklHostName":"sql01",'
                '"cklWebDbSite":"cluster-b","cklWebDbInstance":"MSSQL"}'
            ),
        }
        event_a = _web_event("sql01", "cluster-a", "MSSQL")
        event_b = _web_event("sql01", "cluster-b", "MSSQL")
        self.assertTrue(hosts_svc.host_matches_ingest(host_a, event_a))
        self.assertFalse(hosts_svc.host_matches_ingest(host_a, event_b))
        self.assertTrue(hosts_svc.host_matches_ingest(host_b, event_b))
        self.assertFalse(hosts_svc.host_matches_ingest(host_b, event_a))

    def test_web_ingest_does_not_match_plain_host(self):
        plain = {"hostname": "sql01", "web_or_database": False, "metadata": "{}"}
        self.assertFalse(hosts_svc.host_matches_ingest(plain, _web_event("sql01", "c", "i")))

    def test_plain_ingest_does_not_match_web_host(self):
        web_host = {
            "hostname": "sql01",
            "web_or_database": True,
            "metadata": (
                '{"cklWebOrDatabase":"true","cklHostName":"sql01",'
                '"cklWebDbSite":"c","cklWebDbInstance":"i"}'
            ),
        }
        self.assertFalse(hosts_svc.host_matches_ingest(web_host, _plain_event("sql01")))

    @patch.object(hosts_svc, "list_hosts")
    def test_find_host_for_ingest_picks_correct_web_asset(self, mock_list):
        hosts = [
            {
                "_key": "h1",
                "hostname": "sql01",
                "web_or_database": True,
                "metadata": (
                    '{"cklWebOrDatabase":"true","cklHostName":"sql01",'
                    '"cklWebDbSite":"a","cklWebDbInstance":"inst1"}'
                ),
            },
            {
                "_key": "h2",
                "hostname": "sql01",
                "web_or_database": True,
                "metadata": (
                    '{"cklWebOrDatabase":"true","cklHostName":"sql01",'
                    '"cklWebDbSite":"b","cklWebDbInstance":"inst1"}'
                ),
            },
        ]
        mock_list.return_value = hosts
        found = hosts_svc.find_host_for_ingest(
            MagicMock(), {}, "ws1", _web_event("sql01", "b", "inst1")
        )
        self.assertEqual(found["_key"], "h2")

    def test_ingest_batch_group_key_splits_web_assets(self):
        a = _web_event("sql01", "site-a", "i1")
        b = _web_event("sql01", "site-b", "i1")
        self.assertNotEqual(
            apply_svc._ingest_batch_group_key(a),
            apply_svc._ingest_batch_group_key(b),
        )
        plain = _plain_event("sql01")
        self.assertEqual(
            apply_svc._ingest_batch_group_key(plain),
            "sql01|rhel_8_stig",
        )


if __name__ == "__main__":
    unittest.main()
