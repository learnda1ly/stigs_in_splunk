"""Tests for workspace collection metadata REST service."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import collection_metadata as meta_svc  # noqa: E402


class CollectionMetadataNormalizeTests(unittest.TestCase):
    def test_empty_when_field_missing(self):
        self.assertEqual(meta_svc.parse_metadata_from_collection({}), {})

    def test_rejects_non_object_stored(self):
        with self.assertRaises(ValueError):
            meta_svc.parse_metadata_from_collection({"metadata": "[]"})

    def test_rejects_non_serializable_values(self):
        with self.assertRaises(ValueError):
            meta_svc.normalize_metadata({"bad": object()})

    def test_merge_removes_null_keys(self):
        merged = meta_svc.merge_metadata(
            {"a": 1, "b": 2}, {"b": None, "c": 3}, replace=False
        )
        self.assertEqual(merged, {"a": 1, "c": 3})

    def test_replace_overwrites(self):
        merged = meta_svc.merge_metadata(
            {"a": 1}, {"b": 2}, replace=True
        )
        self.assertEqual(merged, {"b": 2})


class CollectionMetadataRestTests(unittest.TestCase):
    @patch("services.grants.workspace_context")
    def test_get_requires_read(self, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1", "metadata": '{"rmf": "moderate"}'},
            MagicMock(can_read=True),
            [],
        )
        body = meta_svc.get_metadata(MagicMock(), "ws1", {"user": "u"})
        self.assertEqual(body["stig_collection_id"], "ws1")
        self.assertEqual(body["metadata"]["rmf"], "moderate")

    @patch("services.grants.workspace_context")
    def test_get_denied_without_read(self, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=False),
            [],
        )
        with self.assertRaises(KeyError):
            meta_svc.get_metadata(MagicMock(), "ws1", {"user": "u"})

    @patch("services.grants.workspace_context")
    def test_patch_requires_write(self, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=False),
            [],
        )
        with self.assertRaises(PermissionError):
            meta_svc.patch_metadata(
                MagicMock(),
                "ws1",
                {"metadata": {"owner": "team-a"}},
                "u",
                {"user": "u"},
            )

    @patch("services.grants.workspace_context")
    @patch.object(meta_svc, "kv_client")
    @patch.object(meta_svc, "collections_svc")
    def test_patch_merge_persists(self, mock_collections, mock_kv, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = {
            "_key": "ws1",
            "metadata": '{"existing": true}',
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.update_record.return_value = {"_key": "ws1"}
        mock_kv.kv_record.side_effect = lambda r: r

        with patch.object(meta_svc, "audit") as mock_audit:
            mock_audit.log_event = MagicMock()
            out = meta_svc.patch_metadata(
                MagicMock(),
                "ws1",
                {"metadata": {"new_key": "value"}},
                "owner",
                {"user": "owner"},
            )
        self.assertTrue(out["metadata"]["existing"])
        self.assertEqual(out["metadata"]["new_key"], "value")
        stored = mock_kv.update_record.call_args[0][2]
        self.assertIn("metadata", stored)

    @patch("services.grants.workspace_context")
    @patch.object(meta_svc, "kv_client")
    @patch.object(meta_svc, "collections_svc")
    def test_patch_clear(self, mock_collections, mock_kv, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = {
            "_key": "ws1",
            "metadata": '{"a": 1}',
        }
        coll = MagicMock()
        mock_kv.get_collection.return_value = coll
        mock_kv.update_record.return_value = {"_key": "ws1"}
        mock_kv.kv_record.side_effect = lambda r: r

        with patch.object(meta_svc, "audit"):
            out = meta_svc.patch_metadata(
                MagicMock(),
                "ws1",
                {"clear": True},
                "owner",
                {"user": "owner"},
            )
        self.assertEqual(out["metadata"], {})

    @patch("services.grants.workspace_context")
    @patch.object(meta_svc, "collections_svc")
    def test_patch_invalid_metadata_shape(self, mock_collections, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = {"_key": "ws1"}
        with self.assertRaises(ValueError):
            meta_svc.patch_metadata(
                MagicMock(),
                "ws1",
                {"metadata": ["not", "an", "object"]},
                "owner",
                {"user": "owner"},
            )

    @patch("services.grants.workspace_context")
    @patch.object(meta_svc, "collections_svc")
    def test_patch_requires_body(self, mock_collections, mock_workspace):
        mock_workspace.return_value = (
            {"_key": "ws1"},
            MagicMock(can_read=True, can_write=True),
            [],
        )
        mock_collections.get_collection.return_value = {"_key": "ws1"}
        with self.assertRaises(ValueError):
            meta_svc.patch_metadata(
                MagicMock(),
                "ws1",
                {},
                "owner",
                {"user": "owner"},
            )


if __name__ == "__main__":
    unittest.main()
