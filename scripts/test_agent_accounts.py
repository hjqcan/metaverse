"""Regression checks for preventing an account-bound worker from using another login."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_accounts as accounts


class AccountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.row = {"id": "system", "providerAccountId": "account-a", "home": str(self.home)}
        self.config = {"accounts": {"worker-a": dict(self.row)}}
        self.auth("account-a")

    def auth(self, identity):
        (self.home / "auth.json").write_text(json.dumps({
            "auth_mode": "chatgpt", "tokens": {"account_id": identity}
        }))

    def test_missing_account_does_not_fall_back(self):
        with self.assertRaisesRegex(RuntimeError, "no longer registered"):
            accounts.resolve_account(self.config, {}, "worker-a")

    def test_changed_system_login_is_rejected(self):
        changed = dict(self.row, providerAccountId="account-b")
        with self.assertRaisesRegex(RuntimeError, "identity changed"):
            accounts.resolve_account(self.config, {"system": changed}, "worker-a")

    def test_stale_orca_metadata_cannot_hide_changed_credentials(self):
        self.auth("account-b")
        with self.assertRaisesRegex(RuntimeError, "Cached login identity differs"):
            accounts.resolve_account(self.config, {"system": self.row}, "worker-a")

    def test_child_account_does_not_change_parent_environment(self):
        with patch.dict(os.environ, {"CODEX_HOME": "parent-account"}, clear=True):
            env = accounts.account_env(self.row, "worker-a")
            self.assertEqual(env["CODEX_HOME"], str(self.home))
            self.assertEqual(os.environ["CODEX_HOME"], "parent-account")

    def test_api_credentials_cannot_override_bound_subscription(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy-test-value"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "authentication override"):
                accounts.account_env(self.row, "worker-a")

    def test_non_gpt6_model_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Only GPT-6"):
            accounts.session_args("codex", {}, "gpt-5.6-sol", "high")


if __name__ == "__main__":
    unittest.main()
