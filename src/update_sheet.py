#!/usr/bin/env python3
"""Upsert a profile_summary.py business record in the ``websites`` sheet."""

import argparse
import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

try:
    from logging_config import get_logger
except ModuleNotFoundError:
    from src.logging_config import get_logger

logger = get_logger("update_sheet")
_sheet_thread_lock = threading.Lock()


@contextlib.contextmanager
def _sheet_lock():
    """Serialize Google Sheets reads and appends across local threads and worker processes."""
    lock_path = Path(tempfile.gettempdir()) / "studio_google_sheets.lock"
    with _sheet_thread_lock:
        lock_file = None
        try:
            lock_file = lock_path.open("a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        try:
            yield
        finally:
            if lock_file is not None:
                try:
                    if os.name == "nt":
                        import msvcrt
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    lock_file.close()
                except Exception:
                    pass


def load_business(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read summary JSON {path}: {exc}") from exc
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ValueError(f"{path} must contain a non-empty list of business records")
    record = data[0]
    if not str(record.get("handle", "")).strip():
        raise ValueError(f"{path} does not contain an Instagram handle")
    return record


def update_sheet(record: dict[str, Any], credentials: Path, sheet_name: str = "websites") -> tuple[str, int]:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "Google Sheets dependencies are missing; install gspread and google-auth"
        ) from exc

    if not credentials.is_file():
        raise RuntimeError(f"credentials file not found: {credentials}")

    # gspread uses Drive to resolve the spreadsheet by title, then Sheets to edit it.
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    auth = Credentials.from_service_account_file(str(credentials), scopes=scopes)
    client = gspread.authorize(auth)
    worksheet = client.open(sheet_name).sheet1

    with _sheet_lock():
        handle = str(record["handle"]).strip().lstrip("@").casefold()
        rows = worksheet.get("A:F")
        matching_row = None
        highest_serial = 0
        for row_number, row in enumerate(rows[1:], start=2):
            padded = row + [""] * (6 - len(row))
            if str(padded[0]).strip().isdigit():
                highest_serial = max(highest_serial, int(str(padded[0]).strip()))
            if str(padded[2]).strip().lstrip("@").casefold() == handle:
                matching_row = row_number

        values = [
            record.get("name", ""),
            str(record.get("handle", "")).strip().lstrip("@"),
            record.get("phone", ""),
            record.get("area", ""),
            record.get("followers", ""),
        ]
        if matching_row is not None:
            # RAW prevents phone numbers being coerced to numbers or formulas.
            worksheet.update(range_name=f"B{matching_row}:F{matching_row}", values=[values], value_input_option="RAW")
            return "updated", matching_row

        try:
            col_a = worksheet.col_values(1)
            latest_serials = [int(v.strip()) for v in col_a[1:] if str(v).strip().isdigit()]
            if latest_serials:
                highest_serial = max(highest_serial, max(latest_serials))
        except Exception:
            pass

        serial = highest_serial + 1
        worksheet.append_row([serial, *values], value_input_option="RAW")
        return "added", serial


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    parser.add_argument(
        "--credentials", type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "creds.json",
    )
    parser.add_argument("--sheet-name", default="websites")
    args = parser.parse_args()

    try:
        record = load_business(args.summary_json)
        logger.info("Updating Google Sheet from %s", args.summary_json)
        creds_file = args.credentials
        if not creds_file.is_file():
            fallback_creds = Path(__file__).resolve().parents[1] / "config" / "creds.json"
            if fallback_creds.is_file():
                creds_file = fallback_creds
        action, row_or_serial = update_sheet(record, creds_file, args.sheet_name)
    except Exception as exc:
        logger.exception("Google Sheets update failed: %s", exc)
        return 1

    logger.info(
        f"Business: {record.get('name', '')} | @{str(record.get('handle', '')).lstrip('@')} | "
        f"phone: {record.get('phone', '')} | area: {record.get('area', '')} | "
        f"followers: {record.get('followers', '')}"
    )
    if action == "added":
        logger.info("Google Sheet: added row (serial number %s)", row_or_serial)
    else:
        logger.info("Google Sheet: updated existing row %s", row_or_serial)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
