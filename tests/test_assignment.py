import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models import KV_STIG_ASSIGNMENT_RULES, KV_STIG_HOST_BASELINE_ASSIGNMENTS  # noqa: E402
from services import assignment as assignment_svc  # noqa: E402

WIN11 = "Windows_11_STIG"


def _event(hostname: str, **extra):
    base = {
        "assetName": hostname,
        "benchmarkId": WIN11,
        "asset": {"name": hostname, "ip": extra.pop("ip", "10.1.2.3")},
        "source_product": extra.pop("source_product", "evaluate-stig"),
        "collectionId": extra.pop("collectionId", ""),
        "collectionName": extra.pop("collectionName", ""),
        "package_id": extra.pop("package_id", ""),
        "ruleId": "SV-1",
        "groupId": "V-1",
        "result": "fail",
        "stig": {"stig_id": WIN11, "version": "1"},
        "rule": {
            "rule_id": "SV-1",
            "group_id": "V-1",
            "check_content": "x",
            "fix_text": "y",
        },
    }
    base.update(extra)
    return base


class _FakeColl:
    def __init__(self, rows):
        self._rows = {r["_key"]: dict(r) for r in rows}

    def query_all(self):
        return list(self._rows.values())


class TestAssignmentResolver(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.session = {"user": "admin", "authtoken": "token"}
        self.team_a = "coll_team_a"
        self.team_b = "coll_team_b"
        self.default = "coll_default"

    @patch("services.assignment.collections_svc.ensure_default_collection")
    @patch("services.assignment.settings_svc.get_settings")
    @patch("services.assignment.kv_client.get_collection")
    @patch("services.assignment.kv_client.query_all")
    def test_windows11_two_team_hostname_rules(
        self, mock_query_all, mock_get_coll, mock_settings, mock_default
    ):
        mock_settings.return_value = {"trust_event_collection_id": False}
        mock_default.return_value = {"_key": self.default}
        rules = [
            {
                "_key": "rule_a",
                "priority": 10,
                "enabled": True,
                "name": "Team A W11",
                "target_stig_collection_id": self.team_a,
                "match_json": '{"hostname": "w11-team-a-*", "benchmark_id": "'
                + WIN11
                + '"}',
            },
            {
                "_key": "rule_b",
                "priority": 20,
                "enabled": True,
                "name": "Team B W11",
                "target_stig_collection_id": self.team_b,
                "match_json": '{"hostname": "w11-team-b-*", "benchmark_id": "'
                + WIN11
                + '"}',
            },
        ]

        def _query(coll):
            if coll == KV_STIG_ASSIGNMENT_RULES:
                return rules
            return []

        mock_get_coll.side_effect = lambda _svc, name: name
        mock_query_all.side_effect = _query

        res_a = assignment_svc.resolve_collection_id(
            _event("w11-team-a-host01"), self.service, self.session, audit_resolve=False
        )
        res_b = assignment_svc.resolve_collection_id(
            _event("w11-team-b-host99"), self.service, self.session, audit_resolve=False
        )
        self.assertEqual(res_a["stig_collection_id"], self.team_a)
        self.assertEqual(res_a["reason"], assignment_svc.REASON_RULE)
        self.assertEqual(res_b["stig_collection_id"], self.team_b)

    @patch("services.assignment.collections_svc.ensure_default_collection")
    @patch("services.assignment.settings_svc.get_settings")
    @patch("services.assignment.kv_client.get_collection")
    @patch("services.assignment.kv_client.query_all")
    def test_missing_collection_id_uses_rules_not_event(
        self, mock_query_all, mock_get_coll, mock_settings, mock_default
    ):
        mock_settings.return_value = {"trust_event_collection_id": False}
        mock_default.return_value = {"_key": self.default}
        rules = [
            {
                "_key": "r1",
                "priority": 1,
                "enabled": True,
                "name": "by product",
                "target_stig_collection_id": self.team_a,
                "match_json": '{"source_product": "stigman-watcher", "benchmark_id": "'
                + WIN11
                + '"}',
            }
        ]
        mock_get_coll.side_effect = lambda _svc, name: name
        mock_query_all.side_effect = lambda _coll: rules if _coll == KV_STIG_ASSIGNMENT_RULES else []

        event = _event("host-x", collectionId="wrong-coll-id", source_product="stigman-watcher")
        res = assignment_svc.resolve_collection_id(
            event, self.service, self.session, audit_resolve=False
        )
        self.assertEqual(res["stig_collection_id"], self.team_a)
        self.assertEqual(res["reason"], assignment_svc.REASON_RULE)

    @patch("services.assignment.collections_svc.ensure_default_collection")
    @patch("services.assignment.settings_svc.get_settings")
    @patch("services.assignment.kv_client.get_collection")
    @patch("services.assignment.kv_client.query_all")
    def test_override_beats_rule(
        self, mock_query_all, mock_get_coll, mock_settings, mock_default
    ):
        mock_settings.return_value = {"trust_event_collection_id": False}
        mock_default.return_value = {"_key": self.default}
        rules = [
            {
                "_key": "rule_a",
                "priority": 1,
                "enabled": True,
                "name": "rule",
                "target_stig_collection_id": self.team_a,
                "match_json": "{}",
            }
        ]
        overrides = [
            {
                "_key": "ov1",
                "hostname": "special-host",
                "benchmark_id": WIN11,
                "target_stig_collection_id": self.team_b,
                "expires_at": 0,
            }
        ]

        def _query(coll):
            if coll == KV_STIG_ASSIGNMENT_RULES:
                return rules
            if coll == KV_STIG_HOST_BASELINE_ASSIGNMENTS:
                return overrides
            return []

        mock_get_coll.side_effect = lambda _svc, name: name
        mock_query_all.side_effect = _query

        res = assignment_svc.resolve_collection_id(
            _event("special-host"), self.service, self.session, audit_resolve=False
        )
        self.assertEqual(res["stig_collection_id"], self.team_b)
        self.assertEqual(res["reason"], assignment_svc.REASON_OVERRIDE)

    def test_import_param_beats_all(self):
        forced = "operator-chosen-workspace"
        res = assignment_svc.resolve_collection_id(
            _event("h1", collectionId="ignored-should-not-win"),
            self.service,
            self.session,
            forced_collection_id=forced,
            audit_resolve=False,
        )
        self.assertEqual(res["stig_collection_id"], forced)
        self.assertEqual(res["reason"], assignment_svc.REASON_FORCED)


if __name__ == "__main__":
    unittest.main()
