"""Unit tests for unreviewed rules/assets reports."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import reporting as reporting_svc  # noqa: E402


def _sample_rows():
    return [
        {
            "host_id": "h1",
            "hostname": "alpha",
            "baseline_id": "b1",
            "stig_id": "STIG_A",
            "baseline_title": "STIG A",
            "group_id": "V-1",
            "rule_id": "r1",
            "severity": "high",
            "rule_title": "Rule one",
            "group_title": "",
        },
        {
            "host_id": "h1",
            "hostname": "alpha",
            "baseline_id": "b1",
            "stig_id": "STIG_A",
            "baseline_title": "STIG A",
            "group_id": "V-2",
            "rule_id": "r2",
            "severity": "medium",
            "rule_title": "Rule two",
            "group_title": "",
        },
        {
            "host_id": "h2",
            "hostname": "beta",
            "baseline_id": "b2",
            "stig_id": "STIG_B",
            "baseline_title": "STIG B",
            "group_id": "V-1",
            "rule_id": "r1",
            "severity": "low",
            "rule_title": "Rule one B",
            "group_title": "",
        },
    ]


class TestUnreviewedReports(unittest.TestCase):
    @patch.object(reporting_svc, "_list_unreviewed_rows")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_assets_multi_host_baseline_breakdown(self, mock_require, mock_list):
        mock_require.return_value = {"name": "Lab"}
        mock_list.return_value = (_sample_rows(), {}, {})
        out = reporting_svc.collection_unreviewed_assets(
            MagicMock(), "ws1", {"user": "u", "capabilities": {"stig_read": True}}, {}
        )
        self.assertEqual(out["total_unreviewed"], 3)
        self.assertEqual(out["asset_count"], 2)
        alpha = next(a for a in out["assets"] if a["hostname"] == "alpha")
        self.assertEqual(alpha["unreviewed_count"], 2)
        self.assertEqual(len(alpha["by_baseline"]), 1)
        self.assertEqual(alpha["by_baseline"][0]["unreviewed_count"], 2)
        beta = next(a for a in out["assets"] if a["hostname"] == "beta")
        self.assertEqual(beta["by_baseline"][0]["stig_id"], "STIG_B")

    @patch.object(reporting_svc, "_list_unreviewed_rows")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_rules_groups_by_baseline_and_rule(self, mock_require, mock_list):
        mock_require.return_value = {"name": "Lab"}
        mock_list.return_value = (_sample_rows(), {}, {})
        out = reporting_svc.collection_unreviewed_rules(
            MagicMock(), "ws1", {"user": "u"}, {}
        )
        self.assertEqual(out["total_unreviewed"], 3)
        self.assertEqual(out["rule_count"], 3)
        shared = [
            r for r in out["rules"] if r["rule_id"] == "r1" and r["group_id"] == "V-1"
        ]
        self.assertEqual(len(shared), 2)
        stigs = sorted(r["stig_id"] for r in shared)
        self.assertEqual(stigs, ["STIG_A", "STIG_B"])

    @patch.object(reporting_svc, "_list_unreviewed_rows")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_empty_workspace(self, mock_require, mock_list):
        mock_require.return_value = {"name": "Empty"}
        mock_list.return_value = ([], {}, {})
        assets = reporting_svc.collection_unreviewed_assets(
            MagicMock(), "ws-empty", {"user": "u"}, {}
        )
        rules = reporting_svc.collection_unreviewed_rules(
            MagicMock(), "ws-empty", {"user": "u"}, {}
        )
        self.assertEqual(assets["total_unreviewed"], 0)
        self.assertEqual(assets["assets"], [])
        self.assertEqual(rules["rules"], [])

    @patch.object(reporting_svc.grants_svc, "query_grants")
    @patch.object(reporting_svc.collections_svc, "get_collection")
    @patch.object(reporting_svc.access, "user_can_read_collection")
    def test_acl_denied_raises_key_error(self, mock_can_read, mock_get, mock_grants):
        mock_get.return_value = {"_key": "secret"}
        mock_grants.return_value = []
        mock_can_read.return_value = False
        session = {"user": "bob", "capabilities": {"stig_read": True}}
        with self.assertRaises(KeyError):
            reporting_svc.collection_unreviewed_assets(MagicMock(), "secret", session, {})
        with self.assertRaises(KeyError):
            reporting_svc.collection_unreviewed_rules(MagicMock(), "secret", session, {})

    @patch.object(reporting_svc.kv_client, "query_all")
    @patch.object(reporting_svc.kv_client, "get_collection")
    @patch.object(reporting_svc.hosts_svc, "list_hosts")
    @patch.object(reporting_svc.checklists_svc, "list_checklists")
    @patch.object(reporting_svc.baselines_svc, "list_baselines")
    @patch.object(reporting_svc, "_require_read_collection")
    def test_list_unreviewed_excludes_reviewed_status(
        self,
        mock_require,
        mock_baselines,
        mock_checklists,
        mock_hosts,
        mock_get_coll,
        mock_query_all,
    ):
        mock_require.return_value = {"name": "Lab"}
        mock_baselines.return_value = [
            {"_key": "b1", "stig_id": "STIG_A", "title": "A"}
        ]
        mock_checklists.return_value = [
            {
                "_key": "cl1",
                "host_id": "h1",
                "baseline_id": "b1",
                "stig_collection_id": "ws1",
            }
        ]
        mock_hosts.return_value = [{"_key": "h1", "hostname": "host1"}]
        mock_get_coll.return_value = MagicMock()

        def _query(_coll, q):
            if q.get("checklist_id") == "cl1":
                return [
                    {"status": "not_reviewed", "rule_id": "r1", "group_id": "V-1"},
                    {"status": "open", "rule_id": "r2", "group_id": "V-2"},
                ]
            if q.get("baseline_id") == "b1":
                return [
                    {
                        "baseline_id": "b1",
                        "rule_id": "r1",
                        "group_id": "V-1",
                        "severity": "high",
                    }
                ]
            return []

        mock_query_all.side_effect = _query
        rows, _filters, _ctx = reporting_svc._list_unreviewed_rows(
            MagicMock(), "ws1", {"user": "u"}, {}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rule_id"], "r1")


class TestUnreviewedRowFilters(unittest.TestCase):
    """Query-param narrowing on _list_unreviewed_rows (parity with findings scope filters)."""

    def _run_list(self, query):
        reviews_by_cl = {
            "cl1": [
                {
                    "status": "not_reviewed",
                    "rule_id": "r1",
                    "group_id": "V-1",
                    "baseline_id": "b1",
                },
                {
                    "status": "not_reviewed",
                    "rule_id": "r2",
                    "group_id": "V-2",
                    "baseline_id": "b1",
                },
            ],
            "cl2": [
                {
                    "status": "not_reviewed",
                    "rule_id": "r1",
                    "group_id": "V-1",
                    "baseline_id": "b2",
                },
            ],
        }
        rules_by_baseline = {
            "b1": [
                {
                    "baseline_id": "b1",
                    "rule_id": "r1",
                    "group_id": "V-1",
                    "severity": "high",
                },
                {
                    "baseline_id": "b1",
                    "rule_id": "r2",
                    "group_id": "V-2",
                    "severity": "medium",
                },
            ],
            "b2": [
                {
                    "baseline_id": "b2",
                    "rule_id": "r1",
                    "group_id": "V-1",
                    "severity": "low",
                },
            ],
        }

        def _query(_coll, q):
            if q.get("checklist_id"):
                return reviews_by_cl.get(q["checklist_id"], [])
            if q.get("baseline_id"):
                return rules_by_baseline.get(q["baseline_id"], [])
            return []

        with patch.object(reporting_svc, "_require_read_collection") as mock_require, patch.object(
            reporting_svc.baselines_svc, "list_baselines"
        ) as mock_baselines, patch.object(
            reporting_svc.checklists_svc, "list_checklists"
        ) as mock_checklists, patch.object(
            reporting_svc.hosts_svc, "list_hosts"
        ) as mock_hosts, patch.object(
            reporting_svc.kv_client, "get_collection"
        ) as mock_get_coll, patch.object(
            reporting_svc.kv_client, "query_all"
        ) as mock_query_all:
            mock_require.return_value = {"name": "Lab"}
            mock_baselines.return_value = [
                {"_key": "b1", "stig_id": "STIG_A", "title": "A"},
                {"_key": "b2", "stig_id": "STIG_B", "title": "B"},
            ]
            mock_checklists.return_value = [
                {
                    "_key": "cl1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                    "stig_collection_id": "ws1",
                },
                {
                    "_key": "cl2",
                    "host_id": "h2",
                    "baseline_id": "b2",
                    "stig_collection_id": "ws1",
                },
            ]
            mock_hosts.return_value = [
                {"_key": "h1", "hostname": "alpha-server"},
                {"_key": "h2", "hostname": "beta-box"},
            ]
            mock_get_coll.return_value = MagicMock()
            mock_query_all.side_effect = _query
            return reporting_svc._list_unreviewed_rows(
                MagicMock(), "ws1", {"user": "u"}, query
            )

    def test_filter_baseline_id(self):
        rows, _filters, _ctx = self._run_list({"baseline_id": "b1"})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["baseline_id"] == "b1" for r in rows))

    def test_filter_group_id(self):
        rows, _filters, _ctx = self._run_list({"group_id": "V-1"})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["group_id"] == "V-1" for r in rows))

    def test_filter_hostname_substring(self):
        rows, _filters, _ctx = self._run_list({"hostname": "alpha"})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("alpha" in r["hostname"] for r in rows))

    def test_filter_severity(self):
        rows, _filters, _ctx = self._run_list({"severity": "low"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hostname"], "beta-box")

    def test_status_query_param_ignored_still_not_reviewed_only(self):
        rows, _filters, _ctx = self._run_list({"status": "open"})
        self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
