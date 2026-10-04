"""Review image attachment service and REST."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import types
import unittest
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

_BIN = os.path.join(os.path.dirname(__file__), "..", "package", "bin")
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

if "splunk" not in sys.modules:
    persistconn = types.ModuleType("splunk.persistconn")
    application = types.ModuleType("splunk.persistconn.application")

    class PersistentServerConnectionApplication:  # noqa: D101
        def __init__(self, *args, **kwargs):
            pass

    application.PersistentServerConnectionApplication = (
        PersistentServerConnectionApplication
    )
    splunk = types.ModuleType("splunk")
    splunk.persistconn = persistconn
    sys.modules["splunk"] = splunk
    sys.modules["splunk.persistconn"] = persistconn
    sys.modules["splunk.persistconn.application"] = application

import access  # noqa: E402
from services import review_images as images_svc  # noqa: E402
import stig_rest_handler  # noqa: E402


class _MemColl:
    def __init__(self, rows: Dict[str, Dict[str, Any]]):
        self._rows = rows
        self._seq = 0

    def insert(self, data: Dict[str, Any]) -> str:
        self._seq += 1
        key = f"img{self._seq}"
        self._rows[key] = {**data, "_key": key}
        return key

    def query_by_id(self, key: str) -> Optional[Dict[str, Any]]:
        rec = self._rows.get(key)
        return dict(rec) if rec else None

    def update(self, key: str, data: Dict[str, Any]) -> None:
        if key not in self._rows:
            raise KeyError(key)
        self._rows[key] = {**self._rows[key], **data, "_key": key}

    def delete(self, key: str) -> None:
        self._rows.pop(key, None)


class _KvStub:
    def __init__(self) -> None:
        self.tables: Dict[str, Dict[str, Dict[str, Any]]] = {
            "stig_review_images": {},
            "stig_reviews": {
                "rev1": {
                    "_key": "rev1",
                    "checklist_id": "cl1",
                    "baseline_id": "bl1",
                    "rule_id": "V-1",
                }
            },
            "stig_checklists": {
                "cl1": {
                    "_key": "cl1",
                    "stig_collection_id": "ws1",
                    "host_id": "h1",
                    "baseline_id": "bl1",
                }
            },
            "stig_hosts": {
                "h1": {"_key": "h1", "stig_collection_id": "ws1", "label_ids": "[]"},
            },
        }

    def get_collection(self, _service, name: str) -> _MemColl:
        return _MemColl(self.tables[name])

    def get_by_key(self, coll: _MemColl, key: str) -> Optional[Dict[str, Any]]:
        return coll.query_by_id(key)

    def query_all(
        self, coll: _MemColl, query: Optional[Dict[str, Any]] = None
    ) -> list:
        query = query or {}
        out = []
        for rec in coll._rows.values():
            if all(rec.get(k) == v for k, v in query.items()):
                out.append(dict(rec))
        return out

    def insert_record(self, coll: _MemColl, record: Dict[str, Any]) -> Dict[str, Any]:
        key = coll.insert(dict(record))
        stored = coll.query_by_id(key)
        if not stored:
            raise RuntimeError("insert failed")
        return stored

    def delete_record(self, coll: _MemColl, key: str) -> None:
        coll.delete(key)

    def kv_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return record


def _write_ctx():
    return access.WorkspaceAccess(
        can_read=True,
        can_write=True,
        manage_grants=False,
        edit_collection=False,
        edit_access_principals=False,
        grant_role="member",
        acl_host_ids=None,
        acl_baseline_ids=None,
        acl_label_ids=None,
        admin_bypass=False,
    )


def _denied_ctx():
    return access.WorkspaceAccess(
        can_read=True,
        can_write=False,
        manage_grants=False,
        edit_collection=False,
        edit_access_principals=False,
        grant_role="restricted",
        acl_host_ids=set(),
        acl_baseline_ids=None,
        acl_label_ids=None,
        admin_bypass=False,
    )


class ReviewImagesServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kv = _KvStub()
        self.session = {"user": "alice", "capabilities": {"stig_write": True, "stig_read": True}}

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch.object(images_svc.review_history_svc, "_context_for_review")
    @patch.object(images_svc.review_history_svc, "require_visible_review")
    @patch.object(images_svc, "_access_for_review")
    @patch.object(images_svc, "_require_writable_review")
    @patch.object(images_svc.kv_client, "get_collection")
    @patch.object(images_svc.kv_client, "insert_record")
    @patch.object(images_svc, "_images_root")
    def test_upload_and_list(
        self,
        mock_root,
        mock_insert,
        mock_get_coll,
        mock_writable,
        mock_access,
        mock_visible,
        mock_ctx,
    ):
        mock_root.return_value = self.tmp
        review = self.kv.tables["stig_reviews"]["rev1"]
        mock_visible.return_value = review
        mock_writable.return_value = (review, {"_key": "ws1"}, [])
        mock_access.return_value = ({"_key": "ws1"}, _write_ctx(), [])
        mock_ctx.return_value = {
            "stig_collection_id": "ws1",
            "checklist_id": "cl1",
            "host_id": "h1",
            "baseline_id": "bl1",
            "group_id": "",
            "rule_id": "V-1",
            "rule_version": "",
        }
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )

        coll = _MemColl(self.kv.tables["stig_review_images"])
        mock_get_coll.return_value = coll

        def _insert(_coll, record):
            return self.kv.insert_record(_coll, record)

        mock_insert.side_effect = _insert

        created = images_svc.create_review_image(
            MagicMock(),
            "rev1",
            {
                "filename": "dot.png",
                "content_type": "image/png",
                "content_base64": base64.b64encode(png).decode("ascii"),
            },
            "alice",
            self.session,
        )
        self.assertEqual(created["filename"], "dot.png")
        self.assertTrue(created["_key"])
        blob_path = os.path.join(self.tmp, f"{created['_key']}.bin")
        self.assertTrue(os.path.isfile(blob_path))

        with patch.object(images_svc.kv_client, "query_all") as mock_query:
            mock_query.return_value = [
                {
                    "_key": created["_key"],
                    "review_id": "rev1",
                    "filename": "dot.png",
                    "content_type": "image/png",
                    "byte_size": len(png),
                    "created_at": 1,
                    "created_by": "alice",
                }
            ]
            listed = images_svc.list_review_images(MagicMock(), "rev1", self.session)
        self.assertEqual(len(listed["images"]), 1)
        self.assertEqual(
            listed["images"][0]["download_path"],
            f"stig_reviews/rev1/images/{created['_key']}",
        )

    @patch.object(images_svc.review_history_svc, "require_visible_review")
    @patch.object(images_svc, "_access_for_review")
    def test_list_denied_by_acl(self, mock_access, mock_visible):
        mock_visible.return_value = self.kv.tables["stig_reviews"]["rev1"]
        mock_access.side_effect = KeyError("rev1")
        with self.assertRaises(KeyError):
            images_svc.list_review_images(MagicMock(), "rev1", self.session)


class ReviewImagesRestTests(unittest.TestCase):
    def _session(self):
        return {
            "authtoken": "token",
            "user": "alice",
            "capabilities": {"stig_read": True, "stig_write": True},
        }

    def _dispatch(self, rest_path: str, method="GET", body=None):
        handler = stig_rest_handler.StigRestHandler("", "")
        payload = {
            "method": method,
            "session": self._session(),
            "rest_path": rest_path,
            "query": {},
        }
        if body is not None:
            payload["payload"] = json.dumps(body)
        with patch.object(stig_rest_handler.kv_client, "connect", return_value=MagicMock()):
            return handler.handle(json.dumps(payload))

    @patch.object(stig_rest_handler.review_images_svc, "list_review_images")
    def test_list_route(self, mock_list):
        mock_list.return_value = {"review_id": "r1", "images": []}
        resp = self._dispatch("/stig_reviews/r1/images")
        self.assertEqual(resp["status"], 200)
        mock_list.assert_called_once()

    @patch.object(stig_rest_handler.review_images_svc, "list_review_images")
    def test_acl_denial_is_404(self, mock_list):
        mock_list.side_effect = KeyError("r1")
        resp = self._dispatch("/stig_reviews/r1/images")
        self.assertEqual(resp["status"], 404)

    @patch.object(stig_rest_handler.review_images_svc, "create_review_image")
    def test_upload_route(self, mock_create):
        mock_create.return_value = {"_key": "i1", "review_id": "r1"}
        body = {"filename": "a.png", "content_type": "image/png", "content_base64": "abc"}
        resp = self._dispatch("/stig_reviews/r1/images", method="POST", body=body)
        self.assertEqual(resp["status"], 201)
        mock_create.assert_called_once()

    @patch.object(stig_rest_handler.review_images_svc, "create_review_image")
    def test_upload_permission_denied_is_403(self, mock_create):
        mock_create.side_effect = PermissionError("stig_write required")
        body = {"filename": "a.png", "content_type": "image/png", "content_base64": "abc"}
        resp = self._dispatch("/stig_reviews/r1/images", method="POST", body=body)
        self.assertEqual(resp["status"], 403)


if __name__ == "__main__":
    unittest.main()
