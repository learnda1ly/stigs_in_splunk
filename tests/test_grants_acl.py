"""Unit tests for workspace grants and ACL filtering."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import access  # noqa: E402


def _session(
    user: str = "alice",
    roles=None,
    *,
    stig_write: bool = False,
    stig_admin: bool = False,
):
    caps = {"stig_read": True}
    if stig_write:
        caps["stig_write"] = True
    if stig_admin:
        caps["stig_admin"] = True
    return {
        "user": user,
        "roles": list(roles or []),
        "capabilities": caps,
    }


class TestGrantRoles(unittest.TestCase):
    def test_legacy_access_principals_member(self):
        coll = {"_key": "c1", "access_principals": '["user:alice"]'}
        ctx = access.resolve_workspace_access(coll, _session("alice"))
        self.assertTrue(ctx.can_read)
        self.assertFalse(ctx.can_write)
        self.assertEqual(ctx.grant_role, "member")

    def test_member_with_stig_write(self):
        coll = {"_key": "c1", "access_principals": '["user:alice"]'}
        ctx = access.resolve_workspace_access(coll, _session("alice", stig_write=True))
        self.assertTrue(ctx.can_write)

    def test_grant_owner_writes_without_stig_write(self):
        coll = {"_key": "c1", "access_principals": "[]"}
        grants = [
            {
                "principal": "user:alice",
                "grant_role": "owner",
                "acl_host_ids": "[]",
                "acl_baseline_ids": "[]",
            }
        ]
        ctx = access.resolve_workspace_access(coll, _session("alice"), grants)
        self.assertTrue(ctx.can_write)
        self.assertTrue(ctx.manage_grants)
        self.assertTrue(ctx.edit_access_principals)

    def test_grant_restricted_acl_filters_checklist(self):
        coll = {"_key": "c1", "access_principals": "[]"}
        grants = [
            {
                "principal": "user:bob",
                "grant_role": "restricted",
                "acl_host_ids": '["host-a"]',
                "acl_baseline_ids": '["base-1"]',
            }
        ]
        ctx = access.resolve_workspace_access(coll, _session("bob", stig_write=True), grants)
        self.assertTrue(ctx.can_read)
        self.assertTrue(ctx.acl_scoped)
        allowed = access.checklist_allowed(
            {"host_id": "host-a", "baseline_id": "base-1"}, ctx
        )
        denied = access.checklist_allowed(
            {"host_id": "host-a", "baseline_id": "base-2"}, ctx
        )
        self.assertTrue(allowed)
        self.assertFalse(denied)

    def test_grant_only_user_without_access_principals(self):
        coll = {"_key": "c1", "access_principals": '["user:other"]'}
        grants = [{"principal": "user:carol", "grant_role": "manager", "acl_host_ids": "[]"}]
        ctx = access.resolve_workspace_access(coll, _session("carol"), grants)
        self.assertTrue(ctx.can_read)
        self.assertTrue(ctx.manage_grants)

    def test_stig_admin_bypass(self):
        coll = {"_key": "c1", "access_principals": "[]"}
        ctx = access.resolve_workspace_access(coll, _session("admin", stig_admin=True))
        self.assertTrue(ctx.admin_bypass)


class TestAclFilters(unittest.TestCase):
    def test_filter_hosts(self):
        ctx = access.WorkspaceAccess(
            can_read=True,
            can_write=True,
            manage_grants=False,
            edit_collection=False,
            edit_access_principals=False,
            grant_role="restricted",
            acl_host_ids={"h1"},
            acl_baseline_ids=None,
            acl_label_ids=None,
        )
        hosts = [{"_key": "h1"}, {"_key": "h2"}]
        self.assertEqual(len(access.filter_hosts(hosts, ctx)), 1)


if __name__ == "__main__":
    unittest.main()
