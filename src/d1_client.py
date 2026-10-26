"""Cloudflare D1 database client adapter with seamless local SQLite fallback."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterator, Sequence

import requests
from dotenv import load_dotenv

# Automatically load .env if present
REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")


def get_current_user() -> str:
    """Return the current user's name for concurrency tracking across Windows and Linux."""
    return (
        os.environ.get("TEAM_MEMBER_NAME")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "teammate"
    ).strip()


class D1Row:
    """A dictionary-like and tuple-like row object matching sqlite3.Row behavior."""

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self._keys = list(data.keys())

    def __getitem__(self, item: str | int) -> Any:
        if isinstance(item, int):
            return self._data[self._keys[item]]
        return self._data[item]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        # Allows dict(row) to work seamlessly
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def keys(self) -> Sequence[str]:
        return self._keys

    def values(self) -> Sequence[Any]:
        return list(self._data.values())

    def items(self) -> Sequence[tuple[str, Any]]:
        return list(self._data.items())

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __repr__(self) -> str:
        return f"D1Row({self._data!r})"


class D1Cursor:
    """Cursor wrapper for Cloudflare D1 query results."""

    def __init__(self, rows: list[D1Row], lastrowid: int | None = None, rowcount: int = 0):
        self._rows = rows
        self._idx = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchall(self) -> list[D1Row]:
        return list(self._rows)

    def fetchone(self) -> D1Row | None:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def __iter__(self) -> Iterator[D1Row]:
        return iter(self._rows)


class D1Connection:
    """Connection to Cloudflare D1 over the HTTPS REST API."""

    def __init__(self, account_id: str, database_id: str, api_token: str):
        self.account_id = account_id
        self.database_id = database_id
        self.api_token = api_token
        self.endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        })

    def _query(self, sql: str, params: Sequence[Any] | None = None) -> D1Cursor:
        # Convert any Path or custom objects to string
        clean_params = []
        if params is not None:
            for p in params:
                if isinstance(p, Path):
                    clean_params.append(str(p))
                elif isinstance(p, (dict, list)):
                    clean_params.append(json.dumps(p))
                else:
                    clean_params.append(p)

        payload = {"sql": sql, "params": clean_params}
        resp = self.session.post(self.endpoint, json=payload, timeout=20)
        if not resp.ok:
            raise RuntimeError(f"Cloudflare D1 query failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        if not data.get("success"):
            errors = data.get("errors", [])
            err_msg = "; ".join(e.get("message", str(e)) for e in errors)
            raise RuntimeError(f"Cloudflare D1 error: {err_msg}")

        result_list = data.get("result", [])
        if not result_list:
            return D1Cursor([])

        first = result_list[0]
        raw_rows = first.get("results", []) or []
        meta = first.get("meta", {}) or {}
        rows = [D1Row(r) for r in raw_rows]
        return D1Cursor(rows, lastrowid=meta.get("last_row_id"), rowcount=meta.get("changes", 0))

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> D1Cursor:
        return self._query(sql, params)

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> None:
        for params in seq_of_params:
            self._query(sql, params)

    def executescript(self, script: str) -> None:
        # Split statements on semicolons outside of strings
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in statements:
            self._query(stmt)

    def commit(self) -> None:
        # D1 auto-commits each query
        pass

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> D1Connection:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class ClosingLocalConnection(sqlite3.Connection):
    """Local SQLite connection that automatically closes on context manager exit."""

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def is_d1_configured() -> bool:
    """Return True if Cloudflare D1 environment variables are set."""
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    database_id = (
        os.environ.get("D1_DATABASE_ID", "").strip()
        or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    )
    return bool(account_id and api_token and database_id)


def get_db_connection(local_db_path: Path | None = None) -> D1Connection | ClosingLocalConnection:
    """Return a Cloudflare D1 connection if configured, otherwise fallback to local SQLite."""
    if is_d1_configured():
        account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
        api_token = os.environ["CLOUDFLARE_API_TOKEN"].strip()
        database_id = (
            os.environ.get("D1_DATABASE_ID", "").strip()
            or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
        )
        return D1Connection(account_id, database_id, api_token)

    db_file = local_db_path or Path(os.environ.get("DASHBOARD_DB", REPO / "dashboard.sqlite3"))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=15, factory=ClosingLocalConnection)
    conn.row_factory = sqlite3.Row
    return conn
