"""Unit tests for KV insert with explicit _key (RMF system package -1)."""

import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import kv_client  # noqa: E402


class TestKvClientExplicitKey(unittest.TestCase):
    def test_insert_record_preserves_explicit_key(self):
        coll = MagicMock()
        coll.data.insert.return_value = "-1"
        coll.data.query_by_id.return_value = {"_key": "-1", "name": "unassigned"}

        stored = kv_client.insert_record(
            coll, {"_key": "-1", "name": "unassigned", "is_system": True}
        )

        coll.data.insert.assert_called_once()
        payload = coll.data.insert.call_args[0][0]
        self.assertEqual(payload.get("_key"), "-1")
        self.assertEqual(stored["_key"], "-1")
