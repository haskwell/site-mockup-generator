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
from src.pipeline_common import REPO_ROOT

REPO = REPO_ROOT
try:
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
except ImportError:
    pass


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


_cached_d1_session: requests.Session | None = None
_cached_d1_token: str | None = None


def get_shared_d1_session(api_token: str) -> requests.Session:
    """Return a shared requests.Session with connection pooling for Cloudflare D1."""
    global _cached_d1_session, _cached_d1_token
    if _cached_d1_session is not None and _cached_d1_token == api_token:
        return _cached_d1_session

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=2,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    })
    _cached_d1_session = session
    _cached_d1_token = api_token
    return session


class D1Connection:
    """Connection to Cloudflare D1 over the HTTPS REST API."""

    def __init__(self, account_id: str, database_id: str, api_token: str):
        self.account_id = account_id
        self.database_id = database_id
        self.api_token = api_token
        self.endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        )
        self.session = get_shared_d1_session(api_token)

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
        resp = self.session.post(self.endpoint, json=payload, timeout=10)
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
        # Split statements on semicolons outside of string literals and comments
        statements = []
        current = []
        in_single = False
        in_double = False
        in_comment = False
        for i, char in enumerate(script):
            if in_comment:
                current.append(char)
                if char == "\n":
                    in_comment = False
                continue
            if char == "-" and i + 1 < len(script) and script[i + 1] == "-" and not in_single and not in_double:
                in_comment = True
                current.append(char)
                continue
            if char == "'" and not in_double:
                in_single = not in_single
                current.append(char)
            elif char == '"' and not in_single:
                in_double = not in_double
                current.append(char)
            elif char == ";" and not in_single and not in_double:
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
            else:
                current.append(char)
        last = "".join(current).strip()
        if last:
            statements.append(last)
        for stmt in statements:
            self._query(stmt)

    def commit(self) -> None:
        # D1 auto-commits each query
        pass

    def close(self) -> None:
        # Keep shared pooled session open so TCP/TLS connections persist
        pass

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


_syncing_d1 = False


def is_local_mode() -> bool:
    """Return True if local mode is manually enabled via environment or settings."""
    env_mode = os.environ.get("LOCAL_MODE", "").strip().lower()
    if env_mode in {"1", "true", "yes"}:
        return True
    if env_mode in {"0", "false", "no"}:
        return False
    try:
        db_file = Path(os.environ.get("DASHBOARD_DB", REPO / "dashboard.sqlite3"))
        if db_file.is_file():
            with sqlite3.connect(db_file, timeout=2) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT value FROM settings WHERE key='local_mode'").fetchone()
                if row:
                    return bool(json.loads(row["value"]))
    except Exception:
        pass
    return False


def set_local_mode(enabled: bool) -> None:
    """Manually persist local mode toggle in local SQLite settings."""
    try:
        db_file = Path(os.environ.get("DASHBOARD_DB", REPO / "dashboard.sqlite3"))
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_file, timeout=5) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('local_mode', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(enabled),),
            )
            conn.commit()
    except Exception:
        pass


def set_d1_offline(offline: bool = True) -> None:
    """Deprecated alias for set_local_mode; offline fallback is removed."""
    set_local_mode(offline)


def is_d1_offline() -> bool:
    """Deprecated alias for is_local_mode; offline fallback is removed."""
    return is_local_mode()


def is_d1_configured() -> bool:
    """Return True if Cloudflare D1 environment variables are set and local_mode is not enabled."""
    if is_local_mode():
        return False
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    database_id = (
        os.environ.get("D1_DATABASE_ID", "").strip()
        or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    )
    return bool(account_id and api_token and database_id)


def sync_local_to_d1(
    local_db_path: Path | None = None,
    d1_conn: Any | None = None,
    default_settings: dict[str, Any] | None = None,
) -> int:
    """Merge local SQLite changes back into Cloudflare D1 on manual request."""
    global _syncing_d1
    if _syncing_d1:
        return 0
    db_file = local_db_path or Path(os.environ.get("DASHBOARD_DB", REPO / "dashboard.sqlite3"))
    if not db_file.is_file():
        return 0

    _syncing_d1 = True
    synced = 0
    own_d1 = False
    try:
        if d1_conn is None:
            if not is_d1_configured():
                return 0
            account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
            api_token = os.environ["CLOUDFLARE_API_TOKEN"].strip()
            database_id = (
                os.environ.get("D1_DATABASE_ID", "").strip()
                or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
            )
            d1_conn = D1Connection(account_id, database_id, api_token)
            own_d1 = True

        if isinstance(d1_conn, sqlite3.Connection):
            return 0

        local_conn = sqlite3.connect(db_file, timeout=15)
        local_conn.row_factory = sqlite3.Row
        try:
            tables = {
                r[0]
                for r in local_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            local_settings: dict[str, str] = {}
            if "settings" in tables:
                local_settings = {
                    r["key"]: r["value"]
                    for r in local_conn.execute("SELECT key, value FROM settings").fetchall()
                }

            deleted_leads: list[list[str]] = []
            if "_deleted_leads" in local_settings:
                try:
                    deleted_leads = json.loads(local_settings["_deleted_leads"])
                except Exception:
                    deleted_leads = []
            deleted_set = {(b, h) for b, h in deleted_leads if isinstance(b, str) and isinstance(h, str)}
            for b, h in deleted_set:
                try:
                    d1_conn.execute("DELETE FROM leads WHERE batch=? AND handle=?", (b, h))
                    d1_conn.execute("DELETE FROM revisions WHERE batch=? AND handle=?", (b, h))
                    synced += 1
                except Exception:
                    pass

            if "leads" in tables:
                local_leads = [dict(r) for r in local_conn.execute("SELECT * FROM leads").fetchall()]
                if local_leads:
                    try:
                        remote_rows = {
                            (r["batch"], r["handle"]): dict(r)
                            for r in d1_conn.execute("SELECT * FROM leads").fetchall()
                        }
                    except Exception:
                        remote_rows = {}
                    for lead in local_leads:
                        key = (lead.get("batch", ""), lead.get("handle", ""))
                        if key in deleted_set:
                            continue
                        remote = remote_rows.get(key)
                        should_sync = False
                        if remote is None:
                            should_sync = True
                        else:
                            l_ts = str(lead.get("updated_at") or "")
                            r_ts = str(remote.get("updated_at") or "")
                            if l_ts > r_ts or (l_ts == r_ts and lead != remote):
                                should_sync = True
                        if should_sync:
                            cols = list(lead.keys())
                            placeholders = ",".join("?" for _ in cols)
                            col_names = ",".join(cols)
                            d1_conn.execute(
                                f"INSERT OR REPLACE INTO leads({col_names}) VALUES({placeholders})",
                                list(lead.values()),
                            )
                            synced += 1

            if "revisions" in tables:
                local_revs = [dict(r) for r in local_conn.execute("SELECT * FROM revisions").fetchall()]
                if local_revs:
                    try:
                        remote_revs = [
                            dict(r) for r in d1_conn.execute("SELECT * FROM revisions").fetchall()
                        ]
                    except Exception:
                        remote_revs = []
                    remote_by_id = {r.get("id"): r for r in remote_revs}
                    remote_by_sig = {
                        (r.get("batch"), r.get("handle"), r.get("request"), r.get("created_at")): r
                        for r in remote_revs
                    }
                    for rev in local_revs:
                        if (rev.get("batch", ""), rev.get("handle", "")) in deleted_set:
                            continue
                        sig = (
                            rev.get("batch"),
                            rev.get("handle"),
                            rev.get("request"),
                            rev.get("created_at"),
                        )
                        if sig in remote_by_sig:
                            rem = remote_by_sig[sig]
                            if (
                                rev.get("status") != rem.get("status")
                                or rev.get("applied_at") != rem.get("applied_at")
                                or rev.get("backup_path") != rem.get("backup_path")
                            ):
                                d1_conn.execute(
                                    "UPDATE revisions SET status=?, applied_at=?, backup_path=? WHERE id=?",
                                    (
                                        rev.get("status"),
                                        rev.get("applied_at"),
                                        rev.get("backup_path", ""),
                                        rem["id"],
                                    ),
                                )
                                synced += 1
                        elif rev.get("id") not in remote_by_id:
                            cols = list(rev.keys())
                            placeholders = ",".join("?" for _ in cols)
                            d1_conn.execute(
                                f"INSERT OR REPLACE INTO revisions({','.join(cols)}) VALUES({placeholders})",
                                list(rev.values()),
                            )
                            synced += 1
                        else:
                            cols = [k for k in rev.keys() if k != "id"]
                            placeholders = ",".join("?" for _ in cols)
                            d1_conn.execute(
                                f"INSERT INTO revisions({','.join(cols)}) VALUES({placeholders})",
                                [rev[k] for k in cols],
                            )
                            synced += 1

            if "settings" in tables and local_settings:
                try:
                    remote_settings = {
                        r["key"]: r["value"]
                        for r in d1_conn.execute("SELECT key, value FROM settings").fetchall()
                    }
                except Exception:
                    remote_settings = {}
                try:
                    dirty_keys = set(json.loads(local_settings.get("_dirty_settings", "[]")))
                except Exception:
                    dirty_keys = set()
                defaults_map = default_settings or {}
                for k, v in local_settings.items():
                    if k.startswith("_"):
                        continue
                    is_default = k in defaults_map and v == json.dumps(defaults_map[k])
                    if k not in remote_settings or (
                        v != remote_settings[k] and (k in dirty_keys or not is_default)
                    ):
                        d1_conn.execute(
                            "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (k, v)
                        )
                        synced += 1

            if "logs" in tables:
                local_logs = [dict(r) for r in local_conn.execute("SELECT * FROM logs").fetchall()]
                if local_logs:
                    try:
                        remote_logs = [
                            dict(r) for r in d1_conn.execute("SELECT * FROM logs").fetchall()
                        ]
                    except Exception:
                        remote_logs = []
                    remote_log_sigs = {
                        (r.get("batch"), r.get("handle"), r.get("status"), r.get("line"), r.get("created_at"))
                        for r in remote_logs
                    }
                    remote_log_ids = {r.get("id") for r in remote_logs}
                    for lg in local_logs:
                        sig = (
                            lg.get("batch"),
                            lg.get("handle"),
                            lg.get("status"),
                            lg.get("line"),
                            lg.get("created_at"),
                        )
                        if sig not in remote_log_sigs:
                            if lg.get("id") not in remote_log_ids:
                                cols = list(lg.keys())
                                placeholders = ",".join("?" for _ in cols)
                                d1_conn.execute(
                                    f"INSERT OR REPLACE INTO logs({','.join(cols)}) VALUES({placeholders})",
                                    list(lg.values()),
                                )
                            else:
                                cols = [k for k in lg.keys() if k != "id"]
                                placeholders = ",".join("?" for _ in cols)
                                d1_conn.execute(
                                    f"INSERT INTO logs({','.join(cols)}) VALUES({placeholders})",
                                    [lg[k] for k in cols],
                                )
                            synced += 1

            if "settings" in tables:
                for meta_key in ("_d1_offline_pending", "_dirty_settings", "_deleted_leads"):
                    if meta_key in local_settings:
                        local_conn.execute("DELETE FROM settings WHERE key=?", (meta_key,))
                local_conn.commit()
        finally:
            local_conn.close()
    finally:
        if own_d1 and d1_conn is not None:
            try:
                d1_conn.close()
            except Exception:
                pass
        _syncing_d1 = False
    return synced


def get_db_connection(local_db_path: Path | None = None) -> D1Connection | ClosingLocalConnection:
    """Return Cloudflare D1 connection by default. Return local SQLite only if local mode is manually enabled."""
    db_file = local_db_path or Path(os.environ.get("DASHBOARD_DB", REPO / "dashboard.sqlite3"))
    if is_local_mode():
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_file, timeout=15, factory=ClosingLocalConnection)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        return conn

    if not is_d1_configured():
        raise RuntimeError(
            "Cloudflare D1 credentials are not configured in .env. "
            "Please configure Cloudflare D1 or manually enable Local Mode in Settings."
        )

    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    api_token = os.environ["CLOUDFLARE_API_TOKEN"].strip()
    database_id = (
        os.environ.get("D1_DATABASE_ID", "").strip()
        or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    )
    return D1Connection(account_id, database_id, api_token)
