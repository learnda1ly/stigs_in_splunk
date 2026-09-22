"""Ensure automation documentation paths exist."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOC_PATHS = (
    ROOT / "docs" / "automation.md",
    ROOT / "docs" / "api.md",
    ROOT / "docs" / "openapi.yaml",
    ROOT / "docs" / "watcher-hec.md",
)


class TestAutomationDocs(unittest.TestCase):
    def test_automation_doc_paths_exist(self):
        for path in DOC_PATHS:
            self.assertTrue(path.is_file(), f"missing doc: {path}")
