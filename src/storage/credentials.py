"""Manager for reading, writing, and live-testing Cloudflare D1/R2 and team credentials.

Stores sensitive secrets (CLOUDFLARE_API_TOKEN, R2_SECRET_ACCESS_KEY) in the OS Keyring,
and non-sensitive configurations in config.json in the application root directory next to the executable.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.core.common import REPO_ROOT
from src.storage.d1 import D1Connection, is_d1_configured, is_local_mode, set_d1_offline
from src.storage.r2 import is_r2_configured

logger = logging.getLogger(__name__)

SERVICE_NAME = "StudioApp"
CONFIG_PATH = REPO_ROOT / "config.json"
ENV_PATH = REPO_ROOT / ".env"

SECRET_KEYS = {"CLOUDFLARE_API_TOKEN", "R2_SECRET_ACCESS_KEY"}
CONFIG_KEYS = {
    "CLOUDFLARE_ACCOUNT_ID",
    "D1_DATABASE_ID",
    "CLOUDFLARE_D1_DATABASE_ID",
    "R2_ACCESS_KEY_ID",
    "R2_BUCKET_NAME",
    "TEAM_MEMBER_NAME",
}

_HYDRATED = False


def get_keyring_secret(key: str) -> str | None:
    """Retrieve a secret from the OS Keyring. Returns None if unavailable or on error."""
    try:
        import keyring
        import keyring.errors

        val = keyring.get_password(SERVICE_NAME, key)
        if val:
            return val.strip()
    except Exception as exc:
        logger.debug("Failed to read '%s' from OS Keyring: %s", key, exc)
    return None


def set_keyring_secret(key: str, value: str) -> bool:
    """Store a secret in the OS Keyring. Returns True on success, False on failure."""
    if not value:
        return delete_keyring_secret(key)
    try:
        import keyring
        import keyring.errors

        keyring.set_password(SERVICE_NAME, key, value.strip())
        return True
    except Exception as exc:
        logger.warning("Failed to store '%s' in OS Keyring: %s", key, exc)
        return False


def delete_keyring_secret(key: str) -> bool:
    """Delete a secret from the OS Keyring. Returns True on success, False on failure."""
    try:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass
        return True
    except Exception as exc:
        logger.debug("Failed to delete '%s' from OS Keyring: %s", key, exc)
        return False


def load_root_config() -> dict[str, str]:
    """Read non-sensitive configuration from config.json in the application root."""
    if not CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v).strip() for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", CONFIG_PATH, exc)
    return {}


def save_root_config(data: dict[str, str]) -> None:
    """Write non-sensitive configuration to config.json in the application root."""
    existing = load_root_config()
    for k, v in data.items():
        if k in SECRET_KEYS:
            continue  # Never write sensitive secrets to config.json
        if v:
            existing[k] = v.strip()
        elif k in existing:
            del existing[k]

    CONFIG_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def read_raw_env_file() -> dict[str, str]:
    """Parse key-value pairs directly from .env file if it exists."""
    result: dict[str, str] = {}
    if not ENV_PATH.is_file():
        return result
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def scrub_env_secrets(secrets_to_remove: set[str] | None = None) -> None:
    """Remove sensitive keys from .env while preserving non-sensitive config and comments."""
    if not ENV_PATH.is_file():
        return
    targets = secrets_to_remove or SECRET_KEYS
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            if k.strip() in targets:
                # Replace with empty placeholder comment or skip
                continue
        new_lines.append(line)
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def migrate_env_secrets_to_keyring() -> None:
    """One-time migration: migrate plaintext secrets from .env into OS Keyring."""
    if not ENV_PATH.is_file():
        return
    raw_env = read_raw_env_file()
    migrated_keys = set()

    for secret_key in SECRET_KEYS:
        val = raw_env.get(secret_key, "").strip()
        if val:
            # Attempt to save to OS Keyring
            if set_keyring_secret(secret_key, val):
                migrated_keys.add(secret_key)
                logger.info("Migrated secret '%s' from .env into OS Keyring.", secret_key)

    # If any secrets were successfully placed in the keyring, scrub them from .env
    if migrated_keys:
        scrub_env_secrets(migrated_keys)

    # Also sync any root config values to config.json if not present
    non_secret_cfg = {k: v for k, v in raw_env.items() if k in CONFIG_KEYS and v}
    if non_secret_cfg:
        save_root_config(non_secret_cfg)


def hydrate_environment(force: bool = False) -> None:
    """Populate os.environ from .env, config.json in root, and OS Keyring."""
    global _HYDRATED
    if _HYDRATED and not force:
        return

    # 1. Load from .env if present (dotenv)
    if ENV_PATH.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_PATH)
        except Exception:
            pass

    # 2. Load non-sensitive configuration from config.json in root
    root_cfg = load_root_config()
    for k, v in root_cfg.items():
        if v and not os.environ.get(k):
            os.environ[k] = v

    # 3. Retrieve secrets from OS Keyring for any not set in os.environ
    for secret_key in SECRET_KEYS:
        if not os.environ.get(secret_key):
            keyring_val = get_keyring_secret(secret_key)
            if keyring_val:
                os.environ[secret_key] = keyring_val

    # 4. Check for auto-migration of any remaining plaintext secrets in .env
    try:
        migrate_env_secrets_to_keyring()
    except Exception as exc:
        logger.debug("Migration check skipped: %s", exc)

    _HYDRATED = True


# Hydrate immediately on import
hydrate_environment()


def get_credentials_status() -> dict[str, Any]:
    """Return whether D1 and R2 are configured, and return current safe/masked values."""
    hydrate_environment()
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    database_id = (
        os.environ.get("D1_DATABASE_ID", "").strip()
        or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    )
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    r2_access = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    r2_bucket = os.environ.get("R2_BUCKET_NAME", "").strip()
    team_member = os.environ.get("TEAM_MEMBER_NAME", "").strip()

    return {
        "d1_configured": is_d1_configured(),
        "r2_configured": is_r2_configured(),
        "local_mode": is_local_mode(),
        "account_id": account_id,
        "database_id": database_id,
        "has_api_token": bool(api_token),
        "r2_access_key": r2_access,
        "has_r2_secret": bool(r2_secret),
        "r2_bucket_name": r2_bucket,
        "team_member_name": team_member,
    }


def test_d1_connection(account_id: str, database_id: str, api_token: str) -> None:
    """Validate D1 credentials against Cloudflare API."""
    if not (account_id and database_id and api_token):
        raise ValueError("Cloudflare Account ID, Database ID, and API Token are all required.")

    conn = D1Connection(account_id, database_id, api_token)
    try:
        cur = conn.execute("SELECT 1 AS ok")
        row = cur.fetchone()
        if not row or row["ok"] != 1:
            raise RuntimeError("Cloudflare D1 did not return the expected test query response.")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def update_env_file(key_values: dict[str, str]) -> None:
    """Write or update keys in the local .env file, preserving other contents."""
    existing_lines: list[str] = []
    if ENV_PATH.is_file():
        existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _ = stripped.split("=", 1)
            key = key.strip()
            if key in key_values:
                new_lines.append(f"{key}={key_values[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, val in key_values.items():
        if key not in updated_keys and val:
            new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def save_credentials(data: dict[str, str]) -> dict[str, Any]:
    """Test credentials, update os.environ, store secrets in OS Keyring, and write config.json in root."""
    account_id = data.get("account_id", "").strip()
    database_id = data.get("database_id", "").strip()
    api_token = (
        data.get("api_token", "").strip()
        or os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    )

    r2_access = data.get("r2_access_key", "").strip()
    r2_secret = (
        data.get("r2_secret_key", "").strip()
        or os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    )
    r2_bucket = data.get("r2_bucket_name", "").strip()
    team_member = data.get("team_member_name", "").strip()

    # 1. Test D1 live connection
    test_d1_connection(account_id, database_id, api_token)

    # 2. Update memory os.environ
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = account_id
    os.environ["D1_DATABASE_ID"] = database_id
    os.environ["CLOUDFLARE_API_TOKEN"] = api_token
    if r2_access:
        os.environ["R2_ACCESS_KEY_ID"] = r2_access
    if r2_secret:
        os.environ["R2_SECRET_ACCESS_KEY"] = r2_secret
    if r2_bucket:
        os.environ["R2_BUCKET_NAME"] = r2_bucket
    if team_member:
        os.environ["TEAM_MEMBER_NAME"] = team_member

    # 3. Store sensitive secrets in OS Keyring
    keyring_success = True
    if api_token:
        if not set_keyring_secret("CLOUDFLARE_API_TOKEN", api_token):
            keyring_success = False
    if r2_secret:
        if not set_keyring_secret("R2_SECRET_ACCESS_KEY", r2_secret):
            keyring_success = False

    # 4. Save non-sensitive configuration to config.json in root folder
    root_cfg = {
        "CLOUDFLARE_ACCOUNT_ID": account_id,
        "D1_DATABASE_ID": database_id,
    }
    if r2_access:
        root_cfg["R2_ACCESS_KEY_ID"] = r2_access
    if r2_bucket:
        root_cfg["R2_BUCKET_NAME"] = r2_bucket
    if team_member:
        root_cfg["TEAM_MEMBER_NAME"] = team_member
    save_root_config(root_cfg)

    # 5. Handle .env file
    # If keyring succeeded, scrub secrets from .env so they are not stored in plaintext.
    # If keyring failed (fallback), keep them in .env so user configuration is preserved.
    if keyring_success:
        scrub_env_secrets()
        # Keep non-sensitive keys in .env if .env exists
        if ENV_PATH.is_file():
            update_env_file(root_cfg)
    else:
        to_write = dict(root_cfg)
        to_write["CLOUDFLARE_API_TOKEN"] = api_token
        if r2_secret:
            to_write["R2_SECRET_ACCESS_KEY"] = r2_secret
        update_env_file(to_write)

    # Reset any cached clients & offline state
    set_d1_offline(False)
    import src.storage.r2 as r2s

    r2s._cached_s3_client = None
    r2s._cached_s3_creds = None

    import src.storage.d1 as d1c

    d1c._cached_d1_session = None

    return {
        "ok": True,
        "message": "Connected to Cloudflare D1 successfully!",
        "status": get_credentials_status(),
    }
