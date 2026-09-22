"""SplunkUI transfer page REST path contract."""

from __future__ import annotations

import os
import unittest

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
_UI_MARKERS = [
    "/export-to/",
    "/clone",
    "host_ids",
    "Transfer assets",
    "Clone workspace",
]
_BUNDLE_MARKERS = [
    "export-to",
    "/clone",
    "host_ids",
    "Transfer assets",
    "Clone workspace",
]


class TestTransferUiContract(unittest.TestCase):
    def test_transfer_app_source_markers(self) -> None:
        path = os.path.join(_REPO_ROOT, "ui", "src", "pages", "TransferApp.jsx")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for marker in _UI_MARKERS:
            self.assertIn(marker, src, "missing UI REST marker: " + marker)

    def test_transfer_bundle_markers(self) -> None:
        path = os.path.join(
            _REPO_ROOT, "package", "appserver", "static", "ui", "transfer.js"
        )
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for marker in _BUNDLE_MARKERS:
            self.assertIn(marker, src, "missing built bundle marker: " + marker)

    def test_transfer_view_loader_wires_bundle(self) -> None:
        loader = os.path.join(
            _REPO_ROOT, "package", "appserver", "static", "stig_transfer_ui.js"
        )
        with open(loader, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("ui/transfer.js", src)


if __name__ == "__main__":
    unittest.main()
