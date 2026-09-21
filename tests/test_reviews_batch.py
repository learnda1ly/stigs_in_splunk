"""Unit tests for stig_reviews batch update."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import reviews as reviews_svc  # noqa: E402


class TestBatchUpdateReviews(unittest.TestCase):
    def test_rejects_non_array(self):
        with self.assertRaises(ValueError):
            reviews_svc.batch_update_reviews(MagicMock(), {}, "u", {})

    def test_rejects_empty_batch(self):
        with self.assertRaises(ValueError):
            reviews_svc.batch_update_reviews(
                MagicMock(), {"reviews": []}, "u", {}
            )

    def test_partial_success_mixed_outcomes(self):
        service = MagicMock()
        session = {"user": "alice"}

        def fake_update(service, key, body, username, session):
            if key == "ok":
                return {"_key": "ok", "status": body.get("status", "open")}
            if key == "missing":
                raise KeyError(key)
            if key == "denied":
                raise PermissionError("access denied")
            raise ValueError("bad status")

        with patch.object(reviews_svc, "update_review", side_effect=fake_update):
            result = reviews_svc.batch_update_reviews(
                service,
                {
                    "reviews": [
                        {"_key": "ok", "status": "open"},
                        {"_key": "missing", "status": "open"},
                        {"_key": "denied", "comments": "x"},
                        {"_key": "bad", "status": "nope"},
                        {"status": "open"},
                        {"_key": "noop"},
                    ]
                },
                "alice",
                session,
            )

        self.assertEqual(result["summary"]["total"], 6)
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertEqual(result["summary"]["failed"], 5)
        self.assertEqual(len(result["updated"]), 1)
        self.assertEqual(result["updated"][0]["_key"], "ok")
        codes = {e.get("code") for e in result["errors"] if "code" in e}
        self.assertIn("not_found", codes)
        self.assertIn("forbidden", codes)
        self.assertIn("invalid", codes)

    def test_accepts_updates_alias(self):
        service = MagicMock()
        with patch.object(
            reviews_svc,
            "update_review",
            return_value={"_key": "a", "status": "open"},
        ) as mock_update:
            result = reviews_svc.batch_update_reviews(
                service,
                {"updates": [{"_key": "a", "status": "open"}]},
                "bob",
                {},
            )
        self.assertEqual(result["summary"]["succeeded"], 1)
        mock_update.assert_called_once()

if __name__ == "__main__":
    unittest.main()
