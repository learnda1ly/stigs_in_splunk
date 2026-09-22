"""SplunkUI labels page references persist REST paths used by the handler."""

from __future__ import annotations

import os
import unittest


class TestLabelsUiContract(unittest.TestCase):
    def test_labels_app_rest_markers(self) -> None:
        root = os.path.join(os.path.dirname(__file__), "..", "ui", "src", "pages")
        path = os.path.join(root, "LabelsApp.jsx")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        markers = [
            'apiGet("stig_collections/" + cid + "/labels")',
            '"/assets"',
            'apiFetch("stig_hosts/" + hostId',
            "Asset labels",
        ]
        for marker in markers:
            self.assertIn(marker, src, "missing UI REST marker: " + marker)


if __name__ == "__main__":
    unittest.main()
