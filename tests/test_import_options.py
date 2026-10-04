"""Collection import options policy and ingest application."""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import import_options as import_options_svc  # noqa: E402
from services import import_policy as import_policy_svc  # noqa: E402


class TestImportOptionsNormalize(unittest.TestCase):
    def test_defaults_match_stig_manager(self):
        policy = import_options_svc.default_policy()
        self.assertEqual(policy["include_unreviewed"], "with_comments")
        self.assertEqual(policy["empty_detail"], "ignored")
        self.assertEqual(policy["status_per_result"]["fail"], "saved")

    def test_invalid_status_per_result_raises(self):
        with self.assertRaises(ValueError):
            import_options_svc.normalize_policy(
                {"status_per_result": {"fail": "bogus"}}
            )


class TestImportPolicyEvents(unittest.TestCase):
    def test_never_skips_unreviewed(self):
        policy = import_options_svc.default_policy()
        policy["include_unreviewed"] = "never"
        event = {"result": "notchecked", "detail": "note", "comment": ""}
        self.assertFalse(import_policy_svc.should_include_event(event, policy))

    def test_with_comments_requires_text(self):
        policy = import_options_svc.default_policy()
        bare = {"result": "notchecked", "detail": "", "comment": ""}
        with_text = {"result": "notchecked", "detail": "x", "comment": ""}
        self.assertFalse(import_policy_svc.should_include_event(bare, policy))
        self.assertTrue(import_policy_svc.should_include_event(with_text, policy))

    def test_unreviewed_with_comment_informational(self):
        policy = import_options_svc.default_policy()
        event = {"result": "notchecked", "detail": "context only", "comment": ""}
        import_policy_svc.prepare_event_for_import(event, policy)
        self.assertEqual(event["result"], "informational")
        self.assertEqual(event["_status"], "informational")


class TestImportPolicyMerge(unittest.TestCase):
    def test_empty_detail_ignored_keeps_existing(self):
        policy = import_options_svc.default_policy()
        existing = {
            "_key": "r1",
            "finding_details": "keep me",
            "comments": "",
            "status": "open",
            "workflow_state": "draft",
        }
        seed = {"status": "open", "finding_details": "", "comments": ""}
        patch = import_policy_svc.apply_seed_with_policy(
            existing=existing,
            seed=seed,
            event={"result": "fail"},
            policy=policy,
            collection_rec={},
            session={"user": "alice", "roles": []},
            grants=[],
            review_req_policy=import_options_svc.default_policy(),
        )
        self.assertEqual(patch["finding_details"], "keep me")

    def test_empty_detail_imported_clears(self):
        policy = import_options_svc.default_policy()
        policy["empty_detail"] = "imported"
        existing = {
            "_key": "r1",
            "finding_details": "keep me",
            "comments": "",
            "status": "open",
            "workflow_state": "draft",
        }
        seed = {"status": "open", "finding_details": "", "comments": ""}
        patch = import_policy_svc.apply_seed_with_policy(
            existing=existing,
            seed=seed,
            event={"result": "fail"},
            policy=policy,
            collection_rec={},
            session={"user": "alice", "roles": []},
            grants=[],
            review_req_policy=import_options_svc.default_policy(),
        )
        self.assertEqual(patch["finding_details"], "")

    def test_status_per_result_submitted_when_valid(self):
        policy = import_options_svc.default_policy()
        policy["status_per_result"]["fail"] = "submitted"
        existing = {
            "_key": "r1",
            "finding_details": "detail text long enough",
            "comments": "",
            "status": "open",
            "workflow_state": "draft",
        }
        seed = {
            "status": "open",
            "finding_details": "detail text long enough",
            "comments": "",
        }
        patch = import_policy_svc.apply_seed_with_policy(
            existing=existing,
            seed=seed,
            event={"result": "fail"},
            policy=policy,
            collection_rec={},
            session={"user": "alice", "roles": []},
            grants=[],
            review_req_policy=import_options_svc.default_policy(),
        )
        self.assertEqual(patch["workflow_state"], "submitted")


class TestImportOptionsEffective(unittest.TestCase):
    def test_override_blocked_when_customize_disabled(self):
        service = MagicMock()
        rec = {
            "_key": "c1",
            "import_options": json.dumps(
                {"allow_customize_per_import": False, "empty_detail": "ignored"}
            ),
        }
        with patch(
            "services.collections.get_collection", return_value=rec
        ), patch(
            "services.grants.workspace_context",
            return_value=(rec, MagicMock(can_read=True), []),
        ):
            effective = import_options_svc.effective_policy(
                service,
                "c1",
                {"user": "u"},
                override={"empty_detail": "imported"},
                automation=False,
            )
        self.assertEqual(effective["empty_detail"], "ignored")


if __name__ == "__main__":
    unittest.main()
