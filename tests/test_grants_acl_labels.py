"""Grant ACL label scoping and label entity helpers."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import access  # noqa: E402


def _session(user: str = "bob", *, stig_write: bool = False):
    return {
        "user": user,
        "roles": [],
        "capabilities": {"stig_read": True, "stig_write": stig_write},
    }


class TestLabelAcl(unittest.TestCase):
    def test_restricted_label_acl_filters_host(self):
        coll = {"_key": "c1", "access_principals": "[]"}
        grants = [
            {
                "principal": "user:bob",
                "grant_role": "restricted",
                "acl_host_ids": "[]",
                "acl_baseline_ids": "[]",
                "acl_labels": '["lbl-prod"]',
            }
        ]
        ctx = access.resolve_workspace_access(coll, _session("bob"), grants)
        self.assertTrue(ctx.acl_scoped)
        labeled = {"_key": "h1", "label_ids": '["lbl-prod"]'}
        unlabeled = {"_key": "h2", "label_ids": "[]"}
        other = {"_key": "h3", "label_ids": '["lbl-dev"]'}
        self.assertTrue(access.host_allowed(labeled, ctx))
        self.assertFalse(access.host_allowed(unlabeled, ctx))
        self.assertFalse(access.host_allowed(other, ctx))

    def test_checklist_inherits_host_labels(self):
        ctx = access.WorkspaceAccess(
            can_read=True,
            can_write=True,
            manage_grants=False,
            edit_collection=False,
            edit_access_principals=False,
            grant_role="restricted",
            acl_host_ids=None,
            acl_baseline_ids=None,
            acl_label_ids={"lbl-a"},
        )
        host = {"_key": "h1", "label_ids": '["lbl-a"]'}
        cl = {"host_id": "h1", "baseline_id": "b1"}
        self.assertTrue(access.checklist_allowed(cl, ctx, host))
        self.assertFalse(
            access.checklist_allowed(
                cl, ctx, {"_key": "h1", "label_ids": '["lbl-b"]'}
            )
        )

    def test_filter_hosts_hides_unlabeled_when_label_acl(self):
        ctx = access.WorkspaceAccess(
            can_read=True,
            can_write=False,
            manage_grants=False,
            edit_collection=False,
            edit_access_principals=False,
            grant_role="restricted",
            acl_host_ids=None,
            acl_baseline_ids=None,
            acl_label_ids={"lbl-1"},
        )
        hosts = [
            {"_key": "a", "label_ids": '["lbl-1"]'},
            {"_key": "b", "label_ids": "[]"},
        ]
        filtered = access.filter_hosts(hosts, ctx)
        self.assertEqual([h["_key"] for h in filtered], ["a"])


if __name__ == "__main__":
    unittest.main()
