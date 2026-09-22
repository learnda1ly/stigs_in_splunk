"""Tests for stig_hosts asset metadata REST service."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from services import host_metadata as meta_svc  # noqa: E402
from services import collection_metadata as coll_meta_svc  # noqa: E402


class HostMetadataNormalizeTests(unittest.TestCase):
    def test_empty_when_field_missing(self):
        self.assertEqual(coll_meta_svc.parse_metadata_from_collection({}), {})

    def test_rejects_non_object_stored(self):
        with self.assertRaises(ValueError):
            coll_meta_svc.parse_metadata_from_collection({"metadata": "[]"})


class HostMetadataRestTests(unittest.TestCase):
    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_read")
    @patch.object(meta_svc, "kv_client")
    def test_get_empty_metadata(
        self, mock_kv, mock_require_read, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "metadata": "{}",
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = True
        body = meta_svc.get_metadata(MagicMock(), "h1", {"user": "u"})
        self.assertEqual(body["stig_host_id"], "h1")
        self.assertEqual(body["metadata"], {})

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_read")
    @patch.object(meta_svc, "kv_client")
    def test_get_requires_host_acl(
        self, mock_kv, mock_require_read, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = False
        with self.assertRaises(KeyError):
            meta_svc.get_metadata(MagicMock(), "h1", {"user": "u"})

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_write")
    @patch.object(meta_svc, "kv_client")
    def test_patch_requires_write(
        self, mock_kv, mock_require_write, mock_workspace, mock_access
    ):
        mock_require_write.side_effect = PermissionError("access denied")
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
        }
        with self.assertRaises(PermissionError):
            meta_svc.patch_metadata(
                MagicMock(),
                "h1",
                {"metadata": {"owner": "team-a"}},
                "u",
                {"user": "u"},
            )

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_write")
    @patch.object(meta_svc, "kv_client")
    def test_patch_merge_persists(
        self, mock_kv, mock_require_write, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = coll = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "metadata": '{"existing": true}',
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = True
        mock_kv.update_record.return_value = {"_key": "h1"}
        mock_kv.kv_record.side_effect = lambda r: r

        with patch.object(meta_svc, "audit") as mock_audit:
            mock_audit.log_event = MagicMock()
            out = meta_svc.patch_metadata(
                MagicMock(),
                "h1",
                {"metadata": {"new_key": "value"}},
                "owner",
                {"user": "owner"},
            )
        self.assertTrue(out["metadata"]["existing"])
        self.assertEqual(out["metadata"]["new_key"], "value")
        mock_audit.log_event.assert_called_once()
        self.assertEqual(mock_audit.log_event.call_args[0][1], "stig_host_metadata")

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_write")
    @patch.object(meta_svc, "kv_client")
    def test_patch_clear(
        self, mock_kv, mock_require_write, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "metadata": '{"a": 1}',
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = True
        mock_kv.update_record.return_value = {"_key": "h1"}
        mock_kv.kv_record.side_effect = lambda r: r

        with patch.object(meta_svc, "audit"):
            out = meta_svc.patch_metadata(
                MagicMock(),
                "h1",
                {"clear": True},
                "owner",
                {"user": "owner"},
            )
        self.assertEqual(out["metadata"], {})

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_write")
    @patch.object(meta_svc, "kv_client")
    def test_patch_replace_drops_prior_keys(
        self, mock_kv, mock_require_write, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
            "metadata": '{"old": true, "keep": false}',
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = True
        mock_kv.update_record.return_value = {"_key": "h1"}
        mock_kv.kv_record.side_effect = lambda r: r

        with patch.object(meta_svc, "audit"):
            out = meta_svc.patch_metadata(
                MagicMock(),
                "h1",
                {"replace": True, "metadata": {"only": "new"}},
                "owner",
                {"user": "owner"},
            )
        self.assertEqual(out["metadata"], {"only": "new"})

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_write")
    @patch.object(meta_svc, "kv_client")
    def test_patch_invalid_metadata_shape(
        self, mock_kv, mock_require_write, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = True
        with self.assertRaises(ValueError):
            meta_svc.patch_metadata(
                MagicMock(),
                "h1",
                {"metadata": ["not", "an", "object"]},
                "owner",
                {"user": "owner"},
            )

    @patch("services.host_metadata.access")
    @patch("services.grants.workspace_context")
    @patch("services.grants.require_workspace_write")
    @patch.object(meta_svc, "kv_client")
    def test_patch_rejects_null_metadata(
        self, mock_kv, mock_require_write, mock_workspace, mock_access
    ):
        mock_kv.get_collection.return_value = MagicMock()
        mock_kv.get_by_key.return_value = {
            "_key": "h1",
            "stig_collection_id": "ws1",
        }
        mock_workspace.return_value = ({"_key": "ws1"}, MagicMock(), [])
        mock_access.host_allowed.return_value = True
        with self.assertRaises(ValueError):
            meta_svc.patch_metadata(
                MagicMock(),
                "h1",
                {"metadata": None},
                "owner",
                {"user": "owner"},
            )


if __name__ == "__main__":
    unittest.main()
