"""Unit tests for OS Keyring secrets storage and root folder configuration management."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import keyring
from keyring.backend import KeyringBackend

import src.storage.credentials as creds_mod


class InMemoryKeyring(KeyringBackend):
    """Hermetic in-memory keyring for testing."""

    priority = 10

    def __init__(self):
        self._storage: dict[str, dict[str, str]] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._storage.get(service, {}).get(username)

    def set_password(self, service: str, username: str, password: str) -> None:
        self._storage.setdefault(service, {})[username] = password

    def delete_password(self, service: str, username: str) -> None:
        if service in self._storage and username in self._storage[service]:
            del self._storage[service][username]


class TestKeyringAndCredentials(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_config_path = creds_mod.CONFIG_PATH
        self.orig_env_path = creds_mod.ENV_PATH
        self.orig_environ = dict(os.environ)

        # Point paths to temporary sandbox
        creds_mod.CONFIG_PATH = Path(self.temp_dir) / "config.json"
        creds_mod.ENV_PATH = Path(self.temp_dir) / ".env"

        # Use in-memory keyring
        self.mem_keyring = InMemoryKeyring()
        self.orig_keyring = keyring.get_keyring()
        keyring.set_keyring(self.mem_keyring)

    def tearDown(self):
        creds_mod.CONFIG_PATH = self.orig_config_path
        creds_mod.ENV_PATH = self.orig_env_path
        keyring.set_keyring(self.orig_keyring)
        os.environ.clear()
        os.environ.update(self.orig_environ)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_keyring_set_get_delete(self):
        """Verify basic set, get, and delete operations via keyring helper."""
        self.assertTrue(creds_mod.set_keyring_secret("TEST_SECRET", "super-secret-123"))
        self.assertEqual(creds_mod.get_keyring_secret("TEST_SECRET"), "super-secret-123")

        self.assertTrue(creds_mod.delete_keyring_secret("TEST_SECRET"))
        self.assertIsNone(creds_mod.get_keyring_secret("TEST_SECRET"))

    def test_root_config_storage(self):
        """Verify non-sensitive configs are saved to config.json and secrets are excluded."""
        data = {
            "CLOUDFLARE_ACCOUNT_ID": "acc-123",
            "D1_DATABASE_ID": "d1-456",
            "CLOUDFLARE_API_TOKEN": "should-never-be-saved-here",
            "R2_BUCKET_NAME": "my-bucket",
        }
        creds_mod.save_root_config(data)

        self.assertTrue(creds_mod.CONFIG_PATH.is_file())
        saved_text = creds_mod.CONFIG_PATH.read_text(encoding="utf-8")
        self.assertNotIn("should-never-be-saved-here", saved_text)

        loaded = creds_mod.load_root_config()
        self.assertEqual(loaded["CLOUDFLARE_ACCOUNT_ID"], "acc-123")
        self.assertEqual(loaded["D1_DATABASE_ID"], "d1-456")
        self.assertEqual(loaded["R2_BUCKET_NAME"], "my-bucket")
        self.assertNotIn("CLOUDFLARE_API_TOKEN", loaded)

    def test_hydrate_environment(self):
        """Verify hydrate_environment combines root config.json and OS Keyring into os.environ."""
        # Setup config.json
        creds_mod.save_root_config({
            "CLOUDFLARE_ACCOUNT_ID": "acc-test-789",
            "D1_DATABASE_ID": "db-test-012",
        })
        # Setup OS Keyring secret
        creds_mod.set_keyring_secret("CLOUDFLARE_API_TOKEN", "token-from-keyring-xyz")
        creds_mod.set_keyring_secret("R2_SECRET_ACCESS_KEY", "r2-secret-from-keyring")

        # Clear target env vars
        os.environ.pop("CLOUDFLARE_ACCOUNT_ID", None)
        os.environ.pop("D1_DATABASE_ID", None)
        os.environ.pop("CLOUDFLARE_API_TOKEN", None)
        os.environ.pop("R2_SECRET_ACCESS_KEY", None)

        creds_mod.hydrate_environment(force=True)

        self.assertEqual(os.environ.get("CLOUDFLARE_ACCOUNT_ID"), "acc-test-789")
        self.assertEqual(os.environ.get("D1_DATABASE_ID"), "db-test-012")
        self.assertEqual(os.environ.get("CLOUDFLARE_API_TOKEN"), "token-from-keyring-xyz")
        self.assertEqual(os.environ.get("R2_SECRET_ACCESS_KEY"), "r2-secret-from-keyring")

    def test_migrate_env_secrets_to_keyring(self):
        """Verify one-time migration moves plaintext secrets from .env into OS Keyring."""
        env_content = (
            "CLOUDFLARE_ACCOUNT_ID=acc-migrate-1\n"
            "CLOUDFLARE_API_TOKEN=cf-token-plain\n"
            "D1_DATABASE_ID=d1-db-1\n"
            "R2_SECRET_ACCESS_KEY=r2-secret-plain\n"
            "R2_BUCKET_NAME=mockups\n"
        )
        creds_mod.ENV_PATH.write_text(env_content, encoding="utf-8")

        creds_mod.migrate_env_secrets_to_keyring()

        # 1. Keyring must have the secrets
        self.assertEqual(creds_mod.get_keyring_secret("CLOUDFLARE_API_TOKEN"), "cf-token-plain")
        self.assertEqual(creds_mod.get_keyring_secret("R2_SECRET_ACCESS_KEY"), "r2-secret-plain")

        # 2. .env must NOT contain plaintext secrets
        new_env_content = creds_mod.ENV_PATH.read_text(encoding="utf-8")
        self.assertNotIn("cf-token-plain", new_env_content)
        self.assertNotIn("r2-secret-plain", new_env_content)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID=acc-migrate-1", new_env_content)

        # 3. config.json in root must have non-sensitive values
        root_cfg = creds_mod.load_root_config()
        self.assertEqual(root_cfg.get("CLOUDFLARE_ACCOUNT_ID"), "acc-migrate-1")
        self.assertEqual(root_cfg.get("R2_BUCKET_NAME"), "mockups")

    @patch("src.storage.credentials.test_d1_connection")
    def test_save_credentials_flow(self, mock_test_d1):
        """Verify Web UI save_credentials saves secrets to Keyring and config to root."""
        data = {
            "account_id": "acc-save-999",
            "database_id": "d1-save-888",
            "api_token": "cf-api-token-fresh",
            "r2_access_key": "r2-acc-fresh",
            "r2_secret_key": "r2-sec-fresh",
            "r2_bucket_name": "bucket-fresh",
            "team_member_name": "Alice",
        }

        res = creds_mod.save_credentials(data)
        self.assertTrue(res["ok"])

        # Check Keyring
        self.assertEqual(creds_mod.get_keyring_secret("CLOUDFLARE_API_TOKEN"), "cf-api-token-fresh")
        self.assertEqual(creds_mod.get_keyring_secret("R2_SECRET_ACCESS_KEY"), "r2-sec-fresh")

        # Check Root config.json
        cfg = creds_mod.load_root_config()
        self.assertEqual(cfg["CLOUDFLARE_ACCOUNT_ID"], "acc-save-999")
        self.assertEqual(cfg["D1_DATABASE_ID"], "d1-save-888")
        self.assertEqual(cfg["R2_ACCESS_KEY_ID"], "r2-acc-fresh")
        self.assertEqual(cfg["R2_BUCKET_NAME"], "bucket-fresh")
        self.assertEqual(cfg["TEAM_MEMBER_NAME"], "Alice")
        self.assertNotIn("CLOUDFLARE_API_TOKEN", cfg)
        self.assertNotIn("R2_SECRET_ACCESS_KEY", cfg)

        # Check status response
        status = res["status"]
        self.assertEqual(status["account_id"], "acc-save-999")
        self.assertTrue(status["has_api_token"])
        self.assertTrue(status["has_r2_secret"])


if __name__ == "__main__":
    unittest.main()
