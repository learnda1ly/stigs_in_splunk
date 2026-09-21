"""Unit tests for POA&M export helpers."""

from __future__ import annotations

import os
import sys
import unittest
import zipfile
from io import BytesIO

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from exporters.poam import (  # noqa: E402
    finding_to_poam_row,
    findings_to_poam_rows,
    poam_to_csv,
    poam_to_xlsx_bytes,
)


class TestPoamExport(unittest.TestCase):
    def test_finding_to_poam_row_uses_rule_metadata(self):
        finding = {
            "_key": "rev1",
            "hostname": "web01",
            "group_id": "V-1",
            "rule_id": "SV-1_rule",
            "rule_version": "SV-1r1",
            "severity": "high",
            "stig_id": "Splunk_8",
            "baseline_title": "Splunk Enterprise",
            "finding_details": "Non-compliant",
            "status": "open",
            "checklist_id": "cl1",
            "host_id": "h1",
            "baseline_id": "b1",
            "updated_by": "assessor",
            "updated_at": 1700000000,
        }
        meta = {
            "rule_title": "The app must use TLS",
            "ccis": ["CCI-000366", "CCI-000367"],
        }
        row = finding_to_poam_row(finding, meta, poam_id="1")
        self.assertEqual(row["weakness_id"], "V-1")
        self.assertEqual(row["control_vulnerability_description"], "The app must use TLS")
        self.assertIn("CCI-000366", row["cci"])
        self.assertEqual(row["resources_affected"], "web01")
        self.assertEqual(row["security_checks"], "SV-1r1")

    def test_csv_and_xlsx_outputs(self):
        findings = [
            {
                "hostname": "host-a",
                "group_id": "V-2",
                "rule_id": "r2",
                "severity": "medium",
                "stig_id": "U_RHEL",
                "baseline_id": "b1",
                "status": "open",
            }
        ]
        rows = findings_to_poam_rows(findings, {})
        csv_text = poam_to_csv(rows)
        self.assertIn("Weakness ID", csv_text)
        self.assertIn("V-2", csv_text)
        xlsx = poam_to_xlsx_bytes(rows)
        self.assertTrue(xlsx.startswith(b"PK"))
        with zipfile.ZipFile(BytesIO(xlsx), "r") as archive:
            names = set(archive.namelist())
            self.assertIn("xl/worksheets/sheet1.xml", names)


if __name__ == "__main__":
    unittest.main()
