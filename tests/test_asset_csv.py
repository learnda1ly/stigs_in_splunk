"""Asset CSV import/export (STIG Manager §2.9.2.2–2.9.2.3)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from exporters.asset_csv import (  # noqa: E402
    assets_to_csv,
    parse_asset_csv,
    parse_metadata_cell,
)
from services import asset_csv as asset_csv_svc  # noqa: E402


class TestAssetCsvFormat(unittest.TestCase):
    def test_roundtrip_columns(self):
        rows = [
            {
                "Name": "web-01",
                "Description": "Primary web",
                "IP": "10.0.0.1",
                "FQDN": "web-01.example.mil",
                "MAC": "aa:bb:cc:dd:ee:ff",
                "Non-Computing": "FALSE",
                "STIGs": "RHEL_8_STIG\nAPACHE_STIG",
                "Labels": "Prod\nTier1",
                "Metadata": json.dumps({"owner": "team-a"}),
            }
        ]
        text = assets_to_csv(rows)
        parsed = parse_asset_csv(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["Name"], "web-01")
        self.assertIn("APACHE_STIG", parsed[0]["STIGs"])

    def test_metadata_strings_only(self):
        with self.assertRaises(ValueError):
            parse_metadata_cell('{"k": 1}')


class TestAssetCsvImport(unittest.TestCase):
    def _session(self) -> Dict[str, Any]:
        return {
            "user": "writer",
            "capabilities": {"stig_read": True, "stig_write": True},
        }

    @patch("services.asset_csv.checklists_svc.assign_stig_to_host")
    @patch("services.asset_csv.hosts_svc.create_host")
    @patch("services.asset_csv.hosts_svc.find_host_by_hostname")
    @patch("services.asset_csv.labels_svc.list_labels")
    @patch("services.asset_csv.grants_svc.require_workspace_write")
    def test_validate_only_does_not_create(
        self,
        mock_write,
        mock_list_labels,
        mock_find,
        mock_create,
        mock_assign,
    ):
        mock_list_labels.return_value = []
        mock_find.return_value = None
        csv = (
            "Name,Description,IP,FQDN,MAC,Non-Computing,STIGs,Labels,Metadata\n"
            "host1,desc,1.2.3.4,,,FALSE,,,\n"
        )
        with patch(
            "services.asset_csv.baseline_defaults_svc.resolve_baseline_id",
            return_value=None,
        ):
            out = asset_csv_svc.import_assets_csv(
                MagicMock(),
                "ws1",
                csv,
                "writer",
                self._session(),
                submit=False,
            )
        self.assertFalse(out["submitted"])
        self.assertEqual(out["valid_count"], 1)
        mock_create.assert_not_called()
        mock_assign.assert_not_called()

    @patch("services.asset_csv.checklists_svc.assign_stig_to_host")
    @patch("services.asset_csv.hosts_svc.create_host")
    @patch("services.asset_csv.hosts_svc.find_host_by_hostname")
    @patch("services.asset_csv.labels_svc.list_labels")
    @patch("services.asset_csv.grants_svc.require_workspace_write")
    def test_submit_creates_host(
        self,
        mock_write,
        mock_list_labels,
        mock_find,
        mock_create,
        mock_assign,
    ):
        mock_list_labels.return_value = []
        mock_find.return_value = None
        mock_create.return_value = {"_key": "h1", "hostname": "host1"}
        mock_assign.return_value = ({}, False)
        csv = (
            "Name,Description,IP,FQDN,MAC,Non-Computing,STIGs,Labels,Metadata\n"
            "host1,,,,,FALSE,,,\n"
        )
        with patch(
            "services.asset_csv.baseline_defaults_svc.resolve_baseline_id",
            return_value=None,
        ):
            out = asset_csv_svc.import_assets_csv(
                MagicMock(),
                "ws1",
                csv,
                "writer",
                self._session(),
                submit=True,
            )
        self.assertTrue(out["submitted"])
        self.assertEqual(out["summary"]["created"], 1)
        mock_create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
