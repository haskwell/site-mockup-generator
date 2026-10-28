"""Manager for reading, writing, and live-testing Cloudflare D1/R2 and team credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.pipeline_common import REPO_ROOT
from src.d1_client import D1Connection, is_d1_configured, set_d1_offline, is_local_mode
from src.r2_storage import is_r2_configured

ENV_PATH = REPO_ROOT / ".env"


def get_credentials_status() -> dict[str, Any]:
    """Return whether D1 and R2 are configured, and return current safe/masked values."""
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
    """Test credentials, update os.environ, and write to .env."""
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

    # 3. Update .env file
    to_write = {
        "CLOUDFLARE_ACCOUNT_ID": account_id,
        "D1_DATABASE_ID": database_id,
        "CLOUDFLARE_API_TOKEN": api_token,
    }
    if r2_access:
        to_write["R2_ACCESS_KEY_ID"] = r2_access
    if r2_secret:
        to_write["R2_SECRET_ACCESS_KEY"] = r2_secret
    if r2_bucket:
        to_write["R2_BUCKET_NAME"] = r2_bucket
    if team_member:
        to_write["TEAM_MEMBER_NAME"] = team_member

    update_env_file(to_write)

    # Reset any cached clients & offline state
    set_d1_offline(False)
    import src.r2_storage as r2s

    r2s._cached_s3_client = None
    r2s._cached_s3_creds = None

    import src.d1_client as d1c

    d1c._cached_d1_session = None

    return {
        "ok": True,
        "message": "Connected to Cloudflare D1 successfully!",
        "status": get_credentials_status(),
    }
