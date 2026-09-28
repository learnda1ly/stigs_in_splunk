"""RMF package_id filters on exports, metrics, unreviewed, and apply/reconcile."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import apply as apply_svc  # noqa: E402
from services import checklists as checklists_svc  # noqa: E402
from services import reporting as reporting_svc  # noqa: E402
from services import rmf_packages as rmf_svc  # noqa: E402


class TestExportRmfFilter(unittest.TestCase):
    @patch("services.checklists.rmf_packages_svc.checklist_matches_rmf_package_filter")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    def test_checklist_ids_unfiltered_returns_all(
        self,
        get_coll,
        _grants,
        mock_get_collection,
        mock_query_all,
        mock_get_baseline,
        mock_match,
    ):
        get_coll.return_value = {"_key": "ws1", "name": "Lab"}
        mock_match.return_value = True
        mock_get_baseline.return_value = {"stig_id": "STIG_A"}
        mock_get_collection.side_effect = lambda _s, name: name
        mock_query_all.side_effect = lambda _coll, query=None: (
            [
                {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                },
                {
                    "_key": "cl2",
                    "stig_collection_id": "ws1",
                    "host_id": "h2",
                    "baseline_id": "b1",
                },
            ]
            if query == {"stig_collection_id": "ws1"}
            else [
                {"_key": "h1", "hostname": "a", "stig_collection_id": "ws1"},
                {"_key": "h2", "hostname": "b", "stig_collection_id": "ws1"},
            ]
        )
        service = MagicMock()
        session = {"user": "u", "capabilities": {"stig_read": True}}
        with patch(
            "services.checklists.access.filter_checklists",
            side_effect=lambda records, _ctx, **_: records,
        ), patch(
            "services.checklists._access_context",
            return_value=MagicMock(acl_label_ids=None),
        ):
            ids = checklists_svc.checklist_ids_for_collection_export(
                service, "ws1", session
            )
        self.assertEqual(ids, ["cl1", "cl2"])
        mock_match.assert_not_called()

    @patch("services.checklists.rmf_packages_svc.checklist_matches_rmf_package_filter")
    @patch("services.checklists.baselines_svc.get_baseline")
    @patch("services.checklists.kv_client.query_all")
    @patch("services.checklists.kv_client.get_collection")
    @patch("services.checklists.grants_svc.query_grants", return_value=[])
    @patch("services.checklists.collections_svc.get_collection")
    def test_checklist_ids_filtered_by_package(
        self,
        get_coll,
        _grants,
        mock_get_collection,
        mock_query_all,
        mock_get_baseline,
        mock_match,
    ):
        get_coll.return_value = {"_key": "ws1", "name": "Lab"}
        mock_get_baseline.return_value = {"stig_id": "STIG_A"}

        def _match(_service, rec, _host, _baseline, rmf_id):
            return rec["_key"] == "cl1" and rmf_id == "pkg-1"

        mock_match.side_effect = _match
        mock_get_collection.side_effect = lambda _s, name: name
        mock_query_all.side_effect = lambda _coll, query=None: (
            [
                {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "b1",
                },
                {
                    "_key": "cl2",
                    "stig_collection_id": "ws1",
                    "host_id": "h2",
                    "baseline_id": "b1",
                },
            ]
            if query == {"stig_collection_id": "ws1"}
            else [{"_key": "h1", "hostname": "a"}, {"_key": "h2", "hostname": "b"}]
        )
        service = MagicMock()
        session = {"user": "u", "capabilities": {"stig_read": True}}
        with patch(
            "services.checklists.access.filter_checklists",
            side_effect=lambda records, _ctx, **_: records,
        ), patch(
            "services.checklists._access_context",
            return_value=MagicMock(acl_label_ids=None),
        ):
            ids = checklists_svc.checklist_ids_for_collection_export(
                service, "ws1", session, rmf_package_id="pkg-1"
            )
        self.assertEqual(ids, ["cl1"])


class TestMetaMetricsRmfFilter(unittest.TestCase):
    @patch.object(reporting_svc, "aggregate_metrics")
    @patch.object(reporting_svc, "_rule_meta_index", return_value={})
    @patch.object(reporting_svc.settings_svc, "get_settings")
    @patch.object(reporting_svc.settings_svc, "is_governance_enabled", return_value=True)
    @patch.object(reporting_svc.hosts_svc, "list_hosts")
    @patch.object(reporting_svc.checklists_svc, "list_checklists")
    @patch.object(reporting_svc, "_require_read_collection")
    @patch.object(reporting_svc.kv_client, "query_all")
    @patch.object(reporting_svc.kv_client, "get_collection")
    def test_collection_metrics_filtered_reviews(
        self,
        mock_get_coll,
        mock_query_all,
        mock_require,
        mock_list_cl,
        mock_list_hosts,
        _gov,
        mock_settings,
        _meta,
        mock_aggregate,
    ):
        mock_require.return_value = {"name": "Lab"}
        mock_settings.return_value = {}
        mock_list_cl.return_value = [
            {"_key": "cl1", "host_id": "h1", "baseline_id": "b1"},
            {"_key": "cl2", "host_id": "h2", "baseline_id": "b1"},
        ]
        mock_list_hosts.return_value = [
            {"_key": "h1"},
            {"_key": "h2"},
        ]
        mock_get_coll.return_value = "reviews"
        mock_query_all.side_effect = lambda _coll, query: (
            [{"_key": "r1", "checklist_id": "cl1", "rmf_package_id": "pkg-a", "status": "open"}]
            if query.get("checklist_id") == "cl1"
            else [
                {"_key": "r2", "checklist_id": "cl2", "rmf_package_id": "pkg-b", "status": "open"}
            ]
        )
        mock_aggregate.return_value = {
            "totals": {"hosts": 1, "checklists": 1, "reviews": 1},
            "completion": {},
            "workflow": {},
            "by_status": {},
            "by_severity": {},
            "open_by_severity": {},
        }
        out = reporting_svc.collection_metrics(
            MagicMock(),
            "ws1",
            {"capabilities": {"stig_read": True}},
            {"rmf_package_id": "pkg-a"},
        )
        self.assertEqual(out["filters"]["rmf_package_id"], "pkg-a")
        args = mock_aggregate.call_args
        self.assertEqual(len(args[0][0]), 1)
        self.assertEqual(args[1]["host_count"], 1)
        self.assertEqual(args[1]["checklist_count"], 1)

    @patch.object(reporting_svc, "collection_metrics")
    @patch.object(reporting_svc, "_readable_collections_sorted")
    def test_meta_metrics_passes_filter_unfiltered(
        self, mock_collections, mock_metrics
    ):
        mock_collections.return_value = [{"_key": "ws1", "name": "A"}]
        mock_metrics.return_value = {
            "stig_collection_id": "ws1",
            "totals": {"reviews": 2},
            "completion": {},
            "workflow": {},
            "by_status": {},
            "by_severity": {},
            "open_by_severity": {},
        }
        service = MagicMock()
        session = {"capabilities": {"stig_read": True}}
        reporting_svc.meta_collection_metrics(service, session)
        mock_metrics.assert_called_once_with(service, "ws1", session, {})

    @patch.object(reporting_svc, "collection_metrics")
    @patch.object(reporting_svc, "_readable_collections_sorted")
    def test_meta_metrics_passes_filter_when_set(self, mock_collections, mock_metrics):
        mock_collections.return_value = [{"_key": "ws1", "name": "A"}]
        mock_metrics.return_value = {
            "stig_collection_id": "ws1",
            "totals": {"reviews": 1},
            "completion": {},
            "workflow": {},
            "by_status": {},
            "by_severity": {},
            "open_by_severity": {},
        }
        query = {"rmf_package_id": "pkg-9"}
        service = MagicMock()
        session = {"capabilities": {"stig_read": True}}
        out = reporting_svc.meta_collection_metrics(service, session, query)
        mock_metrics.assert_called_once_with(service, "ws1", session, query)
        self.assertEqual(out["filters"]["rmf_package_id"], "pkg-9")


class TestUnreviewedRmfFilter(unittest.TestCase):
    def test_parse_unreviewed_includes_rmf(self):
        parsed = reporting_svc._parse_unreviewed_filters({"rmf_package_id": "pkg-1"})
        self.assertEqual(parsed["rmf_package_id_filter"], "pkg-1")

    @patch.object(reporting_svc, "kv_client")
    def test_list_unreviewed_filters_by_rmf(self, mock_kv):
        ctx = {
            "checklist_by_id": {
                "cl1": {"host_id": "h1", "baseline_id": "b1", "stig_collection_id": "ws1"},
            },
            "host_by_id": {"h1": {"hostname": "host-a"}},
            "baselines": {"b1": {"stig_id": "STIG", "title": "T"}},
            "severity_index": {},
            "rule_meta_index": {},
        }
        reviews_coll = MagicMock()
        mock_kv.get_collection.return_value = reviews_coll
        mock_kv.query_all.return_value = [
            {"status": "not_reviewed", "rule_id": "r1", "group_id": "V-1", "rmf_package_id": "pkg-a"},
            {"status": "not_reviewed", "rule_id": "r2", "group_id": "V-2", "rmf_package_id": "pkg-b"},
        ]
        rows, filters, _ = reporting_svc._list_unreviewed_rows(
            MagicMock(),
            "ws1",
            {"capabilities": {"stig_read": True}},
            {"rmf_package_id": "pkg-a"},
            ctx=ctx,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(filters["rmf_package_id"], "pkg-a")

    @patch.object(reporting_svc, "kv_client")
    def test_list_unreviewed_unfiltered_returns_all(self, mock_kv):
        ctx = {
            "checklist_by_id": {
                "cl1": {"host_id": "h1", "baseline_id": "b1", "stig_collection_id": "ws1"},
            },
            "host_by_id": {"h1": {"hostname": "host-a"}},
            "baselines": {"b1": {"stig_id": "STIG", "title": "T"}},
            "severity_index": {},
            "rule_meta_index": {},
        }
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.query_all.return_value = [
            {"status": "not_reviewed", "rule_id": "r1", "group_id": "V-1", "rmf_package_id": "pkg-a"},
            {"status": "not_reviewed", "rule_id": "r2", "group_id": "V-2", "rmf_package_id": "pkg-b"},
        ]
        rows, filters, _ = reporting_svc._list_unreviewed_rows(
            MagicMock(), "ws1", {}, {}, ctx=ctx
        )
        self.assertEqual(len(rows), 2)
        self.assertIsNone(filters["rmf_package_id"])


class TestApplyRmfEnrichment(unittest.TestCase):
    @patch("services.apply.checklists_svc.apply_review_seeds", return_value={"updated": 0})
    @patch("services.apply.checklists_svc.ensure_review")
    @patch("services.apply.checklists_svc.create_checklist")
    @patch("services.apply.checklists_svc.find_checklist", return_value=None)
    @patch("services.apply.baselines_svc.ensure_baseline_rule")
    @patch("services.apply._upsert_baseline")
    @patch("services.apply._upsert_host")
    @patch("services.apply.assignment_svc.resolve_collection_id")
    @patch("services.apply.rmf_packages_svc.enrich_finding_events_with_rmf_package_id")
    def test_apply_enriches_before_processing(
        self,
        mock_enrich,
        mock_resolve,
        mock_host,
        mock_baseline,
        _rule,
        _find,
        mock_create,
        _ensure,
        _seeds,
    ):
        mock_resolve.return_value = {"stig_collection_id": "ws1", "reason": "default"}
        mock_host.return_value = ({"_key": "h1", "hostname": "web01"}, False)
        mock_baseline.return_value = ({"_key": "b1"}, False)
        mock_create.return_value = {"_key": "cl1", "baseline_id": "b1", "host_id": "h1"}
        event = {
            "assetName": "web01",
            "benchmarkId": "STIG_A",
            "ruleId": "SV-1",
            "groupId": "V-1",
            "result": "fail",
            "rule": {"rule_id": "SV-1", "group_id": "V-1"},
            "stig": {"stig_id": "STIG_A"},
        }
        with patch("services.apply.checklists_svc._require_collection"):
            apply_svc.apply_finding_events(
                MagicMock(),
                [event],
                "ingest",
                {"capabilities": {"stig_write": True}},
            )
        mock_enrich.assert_called_once()
        enriched_events = mock_enrich.call_args[0][1]
        self.assertEqual(enriched_events[0]["assetName"], "web01")

    @patch.object(rmf_svc, "resolve_package_id", return_value="pkg-42")
    def test_enrich_sets_rmf_on_events(self, _resolve):
        events = [{"assetName": "h1", "benchmarkId": "STIG", "baselineId": ""}]
        rmf_svc.enrich_finding_events_with_rmf_package_id(MagicMock(), events)
        self.assertEqual(events[0]["rmf_package_id"], "pkg-42")


if __name__ == "__main__":
    unittest.main()
