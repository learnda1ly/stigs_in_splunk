import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import baseline_defaults as defaults_svc  # noqa: E402


class TestBaselineDefaultResolution(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.session = {"user": "admin", "authtoken": "t"}

    @patch("services.baseline_defaults.baselines_svc.get_baseline")
    @patch("services.baseline_defaults.baselines_svc.find_baseline_by_stig")
    @patch("services.baseline_defaults.collections_svc.get_collection")
    def test_explicit_baseline_wins(self, mock_coll, mock_find, mock_get):
        mock_get.return_value = {"_key": "explicit", "stig_id": "Example_STIG"}
        bid = defaults_svc.resolve_baseline_id(
            self.service,
            collection_id="coll1",
            explicit_baseline_id="explicit",
            stig_id="Example_STIG",
        )
        self.assertEqual(bid, "explicit")
        mock_coll.assert_not_called()
        mock_find.assert_not_called()

    @patch("services.baseline_defaults.baselines_svc.get_baseline")
    @patch("services.baseline_defaults.baselines_svc.find_baseline_by_stig")
    @patch("services.baseline_defaults.collections_svc.get_collection")
    def test_workspace_default_before_catalog(self, mock_coll, mock_find, mock_get):
        mock_coll.return_value = {
            "_key": "coll1",
            "default_baseline_map": '{"example_stig":"default_rev"}',
        }

        def _get(_svc, key):
            if key == "default_rev":
                return {"_key": "default_rev", "stig_id": "Example_STIG"}
            return None

        mock_get.side_effect = _get
        bid = defaults_svc.resolve_baseline_id(
            self.service,
            collection_id="coll1",
            stig_id="Example_STIG",
        )
        self.assertEqual(bid, "default_rev")
        mock_find.assert_not_called()

    @patch("services.baseline_defaults.baselines_svc.get_baseline")
    @patch("services.baseline_defaults.baselines_svc.find_baseline_by_stig")
    @patch("services.baseline_defaults.collections_svc.get_collection")
    def test_catalog_fallback_when_no_default(self, mock_coll, mock_find, mock_get):
        mock_coll.return_value = {"_key": "coll1", "default_baseline_map": "{}"}
        mock_find.return_value = {"_key": "latest", "stig_id": "Example_STIG"}
        mock_get.return_value = None
        bid = defaults_svc.resolve_baseline_id(
            self.service,
            collection_id="coll1",
            stig_id="Example_STIG",
        )
        self.assertEqual(bid, "latest")


if __name__ == "__main__":
    unittest.main()
