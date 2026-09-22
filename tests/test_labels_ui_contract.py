"""SplunkUI labels page and shipped bundle reference persist REST paths."""

from __future__ import annotations

import os
import unittest

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
_UI_MARKERS = [
    'stig_collections/" + cid + "/labels',
    "/assets",
    'stig_hosts/" + hostId',
    "Asset labels",
]
_BUNDLE_MARKERS = [
    "stig_collections/",
    "/labels/",
    "/assets",
    "stig_hosts/",
    "Asset labels",
]


class TestLabelsUiContract(unittest.TestCase):
    def test_labels_app_source_markers(self) -> None:
        path = os.path.join(_REPO_ROOT, "ui", "src", "pages", "LabelsApp.jsx")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for marker in _UI_MARKERS:
            self.assertIn(marker, src, "missing UI REST marker: " + marker)

    def test_labels_bundle_markers(self) -> None:
        path = os.path.join(
            _REPO_ROOT, "package", "appserver", "static", "ui", "labels.js"
        )
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for marker in _BUNDLE_MARKERS:
            self.assertIn(marker, src, "missing built bundle marker: " + marker)

    def test_labels_view_loader_wires_bundle(self) -> None:
        loader = os.path.join(
            _REPO_ROOT, "package", "appserver", "static", "stig_labels_ui.js"
        )
        with open(loader, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("ui/labels.js", src)


if __name__ == "__main__":
    unittest.main()
