import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "package", "bin"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import setup_readiness as readiness_svc  # noqa: E402


class TestRoleReadiness(unittest.TestCase):
    def test_stig_user_role_ok(self):
        session = {"user": "alice", "roles": ["stig_user"], "capabilities": {}}
        report = readiness_svc.assess_role_readiness(session)
        self.assertTrue(report["ok"])
        self.assertEqual(report["missing"], [])

    def test_missing_role_lists_capability(self):
        session = {"user": "bob", "roles": ["user"], "capabilities": {}}
        report = readiness_svc.assess_role_readiness(session)
        self.assertFalse(report["ok"])
        self.assertTrue(report["missing"])
        self.assertIn("Settings", report["fix_in_splunk"])


class TestOwnershipReadiness(unittest.TestCase):
    def test_writable_local_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = os.path.join(tmp, "stigs_in_splunk")
            local_dir = os.path.join(app_root, "local")
            os.makedirs(local_dir)
            with mock.patch.object(readiness_svc, "_app_paths") as paths_mock:
                paths_mock.return_value = {
                    "app_root": app_root,
                    "local_dir": local_dir,
                    "settings_conf": os.path.join(local_dir, "stigs_in_splunk_settings.conf"),
                    "app_conf": os.path.join(local_dir, "app.conf"),
                }
                report = readiness_svc.assess_ownership_readiness()
            self.assertTrue(report["ok"])
            self.assertIn("chown", report["chown_command"])

    def test_unwritable_local_shows_chown(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = os.path.join(tmp, "stigs_in_splunk")
            local_dir = os.path.join(app_root, "local")
            os.makedirs(local_dir)
            with mock.patch.object(readiness_svc, "_app_paths") as paths_mock:
                paths_mock.return_value = {
                    "app_root": app_root,
                    "local_dir": local_dir,
                    "settings_conf": os.path.join(local_dir, "stigs_in_splunk_settings.conf"),
                    "app_conf": os.path.join(local_dir, "app.conf"),
                }
                with mock.patch("services.setup_readiness.open", side_effect=OSError(13, "Permission denied")):
                    report = readiness_svc.assess_ownership_readiness()
            self.assertFalse(report["ok"])
            self.assertIn("chown -R", report["chown_command"])
            self.assertIn("chown", report["next_action"])


class TestMarkSetupComplete(unittest.TestCase):
    def test_requires_admin(self):
        session = {"user": "user1", "roles": ["user"], "capabilities": {}}
        result = readiness_svc.mark_setup_complete(session)
        self.assertFalse(result["ok"])
        self.assertIn("admin", result["error"].lower())

    def test_admin_writes_is_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_root = os.path.join(tmp, "stigs_in_splunk")
            local_dir = os.path.join(app_root, "local")
            os.makedirs(local_dir)
            app_conf = os.path.join(local_dir, "app.conf")
            with open(app_conf, "w", encoding="utf-8") as handle:
                handle.write("[install]\nis_configured = false\n")
            session = {"user": "admin", "roles": ["admin"], "capabilities": {}}
            with mock.patch.object(readiness_svc, "_app_paths") as paths_mock:
                paths_mock.return_value = {
                    "app_root": app_root,
                    "local_dir": local_dir,
                    "settings_conf": os.path.join(local_dir, "stigs_in_splunk_settings.conf"),
                    "app_conf": app_conf,
                }
                with mock.patch.object(readiness_svc, "assess_ownership_readiness") as own_mock:
                    own_mock.return_value = {"ok": True}
                    result = readiness_svc.mark_setup_complete(session)
            self.assertTrue(result["ok"])
            with open(app_conf, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("is_configured = 1", text)


if __name__ == "__main__":
    unittest.main()
