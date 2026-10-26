#!/usr/bin/env python3
"""One-time migration script to copy local dashboard.sqlite3 to Cloudflare D1."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.d1_client import get_db_connection, is_d1_configured

LOCAL_DB = REPO / "dashboard.sqlite3"


def main() -> int:
    if not is_d1_configured():
        print("ERROR: Cloudflare D1 credentials are not configured in .env.")
        print("Please set CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, and D1_DATABASE_ID in .env first.")
        return 1

    if not LOCAL_DB.is_file():
        print(f"Local database {LOCAL_DB} not found. Nothing to migrate.")
        return 0

    print(f"Opening local SQLite database: {LOCAL_DB}")
    local_conn = sqlite3.connect(LOCAL_DB)
    local_conn.row_factory = sqlite3.Row

    print("Connecting to Cloudflare D1...")
    d1 = get_db_connection()

    # Step 1: Ensure D1 schema exists
    print("Ensuring tables exist on Cloudflare D1...")
    d1.executescript("""
    CREATE TABLE IF NOT EXISTS leads(
        batch TEXT,
        handle TEXT,
        name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        area TEXT DEFAULT '',
        followers TEXT DEFAULT '',
        status TEXT DEFAULT 'queued',
        error TEXT DEFAULT '',
        site_path TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        stage TEXT DEFAULT 'new',
        follow_up TEXT DEFAULT '',
        price TEXT DEFAULT '',
        qa TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        locked_by TEXT DEFAULT '',
        locked_at TEXT DEFAULT '',
        PRIMARY KEY(batch,handle)
    );
    CREATE TABLE IF NOT EXISTS revisions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch TEXT,
        handle TEXT,
        request TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        applied_at TEXT,
        backup_path TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch TEXT,
        handle TEXT,
        status TEXT,
        line TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Step 2: Migrate leads
    leads = [dict(r) for r in local_conn.execute("SELECT * FROM leads").fetchall()]
    print(f"Found {len(leads)} lead(s) in local database.")
    for lead in leads:
        lead.setdefault("locked_by", "")
        lead.setdefault("locked_at", "")
        cols = list(lead.keys())
        placeholders = ",".join("?" for _ in cols)
        col_names = ",".join(cols)
        sql = f"INSERT OR REPLACE INTO leads({col_names}) VALUES({placeholders})"
        d1.execute(sql, list(lead.values()))

    # Step 3: Migrate settings
    settings = [dict(r) for r in local_conn.execute("SELECT * FROM settings").fetchall()]
    print(f"Found {len(settings)} setting(s) in local database.")
    for s in settings:
        d1.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (s["key"], s["value"]))

    # Step 4: Migrate revisions
    try:
        revisions = [dict(r) for r in local_conn.execute("SELECT * FROM revisions").fetchall()]
        print(f"Found {len(revisions)} revision(s) in local database.")
        for rev in revisions:
            cols = list(rev.keys())
            placeholders = ",".join("?" for _ in cols)
            col_names = ",".join(cols)
            sql = f"INSERT OR REPLACE INTO revisions({col_names}) VALUES({placeholders})"
            d1.execute(sql, list(rev.values()))
    except Exception as exc:
        print(f"Note: revisions table migration skipped ({exc})")

    print("\n✅ Migration to Cloudflare D1 completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
