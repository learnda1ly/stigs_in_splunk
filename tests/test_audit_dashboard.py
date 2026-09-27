"""Dashboard SPL for stig_audit_dashboard must extract JSON from _raw."""

from __future__ import annotations

import os
import unittest
import xml.etree.ElementTree as ET


class AuditDashboardSearchTests(unittest.TestCase):
    def test_recent_actions_search_uses_spath_before_table(self) -> None:
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "package",
            "default",
            "data",
            "ui",
            "views",
            "stig_audit_dashboard.xml",
        )
        root = ET.parse(path).getroot()
        queries = [
            (elem.text or "").strip()
            for elem in root.findall(".//search/query")
        ]
        self.assertEqual(len(queries), 3)
        for query in queries:
            self.assertIn("| spath", query, query)
        main = queries[0]
        self.assertLess(main.index("| spath"), main.index("| table"))
        for field in (
            "action",
            "user",
            "object",
            "workspace_id",
            "entity_type",
            "entity_id",
        ):
            self.assertIn(field, main)


if __name__ == "__main__":
    unittest.main()
