import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models import (  # noqa: E402
    KV_STIG_HOST_BASELINE_RMF_OVERRIDES,
    KV_STIG_HOST_RMF_DEFAULTS,
    KV_STIG_REVIEWS,
    KV_STIG_RMF_PACKAGES,
    RMF_SYSTEM_PACKAGE_ID,
)
from services import rmf_packages as rmf_svc  # noqa: E402


class _MemColl:
    def __init__(self):
        self._rows = {}

    def get_by_key(self, key):
        return self._rows.get(key)

    def insert_record(self, coll, record):
        key = record["_key"]
        self._rows[key] = dict(record)
        return self._rows[key]

    def update_record(self, coll, key, record):
        self._rows[key] = dict(record)
        return self._rows[key]

    def delete_record(self, coll, key):
        self._rows.pop(key, None)

    def query_all(self, coll, query=None):
        rows = list(self._rows.values())
        if not query:
            return rows
        out = []
        for rec in rows:
            ok = True
            for field, value in query.items():
                if str(rec.get(field) or "") != str(value):
                    ok = False
                    break
            if ok:
                out.append(rec)
        return out


class TestRmfPackageResolution(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.packages = _MemColl()
        self.defaults = _MemColl()
        self.overrides = _MemColl()
        self.reviews = _MemColl()
        self.session_admin = {"user": "admin", "roles": ["admin"], "capabilities": {}}
        self.session_writer = {
            "user": "writer",
            "roles": ["stig_user"],
            "capabilities": {"stig_write": True},
        }

        def _get_coll(_service, name):
            if name == KV_STIG_RMF_PACKAGES:
                return self.packages
            if name == KV_STIG_HOST_RMF_DEFAULTS:
                return self.defaults
            if name == KV_STIG_HOST_BASELINE_RMF_OVERRIDES:
                return self.overrides
            if name == KV_STIG_REVIEWS:
                return self.reviews
            return _MemColl()

        self.get_coll_patcher = patch(
            "services.rmf_packages.kv_client.get_collection", side_effect=_get_coll
        )
        self.get_coll_patcher.start()
        patcher_insert = patch("services.rmf_packages.kv_client.insert_record")
        patcher_update = patch("services.rmf_packages.kv_client.update_record")
        patcher_delete = patch("services.rmf_packages.kv_client.delete_record")
        patcher_get = patch("services.rmf_packages.kv_client.get_by_key")
        patcher_query = patch("services.rmf_packages.kv_client.query_all")

        def _route_insert(coll, record):
            return coll.insert_record(coll, record)

        def _route_update(coll, key, record):
            return coll.update_record(coll, key, record)

        def _route_delete(coll, key):
            return coll.delete_record(coll, key)

        def _route_get(coll, key):
            return coll.get_by_key(key)

        def _route_query(coll, query=None):
            return coll.query_all(coll, query)

        self.insert = patcher_insert.start()
        self.update = patcher_update.start()
        self.delete = patcher_delete.start()
        self.get_by_key = patcher_get.start()
        self.query_all = patcher_query.start()
        self.insert.side_effect = _route_insert
        self.update.side_effect = _route_update
        self.delete.side_effect = _route_delete
        self.get_by_key.side_effect = _route_get
        self.query_all.side_effect = _route_query

        rmf_svc.ensure_system_package(self.service, "system")
        rmf_svc.create_package(
            self.service,
            {"id": "pkg-a", "name": "Package A"},
            "admin",
            self.session_admin,
        )
        rmf_svc.create_package(
            self.service,
            {"id": "pkg-b", "name": "Package B"},
            "admin",
            self.session_admin,
        )

    def tearDown(self):
        self.get_coll_patcher.stop()

    def test_resolution_order_override_default_unassigned(self):
        rmf_svc.set_host_default(
            self.service, "host01", "pkg-a", "admin", self.session_admin
        )
        rmf_svc.set_baseline_override(
            self.service, "host01", "baseline-x", "pkg-b", "admin", self.session_admin
        )
        self.assertEqual(
            rmf_svc.resolve_package_id(self.service, "host01", "baseline-x", ""),
            "pkg-b",
        )
        self.assertEqual(
            rmf_svc.resolve_package_id(self.service, "host01", "baseline-y", ""),
            "pkg-a",
        )

    def test_unassigned_when_no_assignment(self):
        self.assertEqual(
            rmf_svc.resolve_package_id(self.service, "lonely-host", "bl-1", ""),
            RMF_SYSTEM_PACKAGE_ID,
        )

    def test_id_rename_bulk_updates_references(self):
        rmf_svc.set_host_default(
            self.service, "host01", "pkg-a", "admin", self.session_admin
        )
        rmf_svc.set_baseline_override(
            self.service, "host01", "baseline-x", "pkg-a", "admin", self.session_admin
        )
        self.reviews._rows["rev1"] = {
            "_key": "rev1",
            "rmf_package_id": "pkg-a",
            "checklist_id": "cl1",
        }
        rmf_svc.update_package(
            self.service,
            "pkg-a",
            {"id": "pkg-a-renamed", "name": "Package A renamed"},
            "admin",
            self.session_admin,
        )
        default = self.defaults.get_by_key("host01")
        self.assertEqual(default["package_id"], "pkg-a-renamed")
        override = next(iter(self.overrides._rows.values()))
        self.assertEqual(override["package_id"], "pkg-a-renamed")
        self.assertEqual(self.reviews._rows["rev1"]["rmf_package_id"], "pkg-a-renamed")
        self.assertIsNone(self.packages.get_by_key("pkg-a"))
        self.assertIsNotNone(self.packages.get_by_key("pkg-a-renamed"))

    def test_stig_write_cannot_create_package(self):
        with self.assertRaises(PermissionError):
            rmf_svc.create_package(
                self.service,
                {"id": "pkg-x", "name": "Nope"},
                "writer",
                self.session_writer,
            )


if __name__ == "__main__":
    unittest.main()
