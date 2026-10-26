#!/usr/bin/env python3
"""Migration script to upload all local websites and asset data to Cloudflare R2."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.d1_client import get_db_connection, is_d1_configured
from src.r2_storage import (
    get_preview_url,
    get_s3_client,
    guess_content_type,
    is_r2_configured,
)


def get_default_websites_root() -> Path:
    """Find the configured websites root directory."""
    env_root = os.environ.get("WEBSITES_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    # Try to read from database settings
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT value FROM settings WHERE key='websites_root'").fetchone()
        if row:
            val = json.loads(row["value"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[0])
            if val:
                return Path(val).expanduser().resolve()
    except Exception:
        pass

    return (Path.home() / "websites").resolve()


def upload_directory_to_r2(s3_client, bucket: str, local_dir: Path, r2_prefix: str) -> tuple[int, int]:
    """Recursively upload files from local_dir to R2 under r2_prefix.
    Returns (file_count, byte_count).
    """
    file_count = 0
    byte_count = 0
    if not local_dir.is_dir():
        return 0, 0

    clean_prefix = r2_prefix.strip("/")

    for item in local_dir.rglob("*"):
        if item.is_file():
            # Use as_posix() to ensure forward slashes across all platforms
            rel = item.relative_to(local_dir).as_posix()
            key = f"{clean_prefix}/{rel}"
            ct = guess_content_type(item)
            size = item.stat().st_size
            with item.open("rb") as f:
                s3_client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType=ct,
                )
            file_count += 1
            byte_count += size

    return file_count, byte_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload local website and asset data to Cloudflare R2.")
    parser.add_argument(
        "websites_root",
        nargs="?",
        default=None,
        help="Path to the local websites directory (defaults to configured websites_root)",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        default=True,
        help="Update lead site_path records in database to point to R2 preview URLs (default: True)",
    )
    args = parser.parse_args()

    if not is_r2_configured():
        print("ERROR: Cloudflare R2 is not configured in .env.")
        print("Please configure CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME first.")
        return 1

    root = Path(args.websites_root).expanduser().resolve() if args.websites_root else get_default_websites_root()
    if not root.is_dir():
        print(f"ERROR: Websites root directory not found at: {root}")
        print("Please specify the correct path: python scripts/migrate_to_r2.py /path/to/websites")
        return 1

    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    db = get_db_connection() if args.update_db else None

    print(f"📦 Source directory: {root}")
    print(f"☁️  Target R2 Bucket: {bucket}")
    print(f"🗄️  Database Target: {'Cloudflare D1' if is_d1_configured() else 'Local SQLite'}")
    print("=" * 60)

    total_files = 0
    total_bytes = 0
    accounts_processed = 0

    # Iterate over batch date folders (e.g. 2026-10-11)
    batch_dirs = sorted([d for d in root.iterdir() if d.is_dir()])
    if not batch_dirs:
        print(f"No batch folders found in {root}.")
        return 0

    for batch_dir in batch_dirs:
        batch_name = batch_dir.name
        account_dirs = sorted([d for d in batch_dir.iterdir() if d.is_dir()])
        if not account_dirs:
            continue

        print(f"\n📁 Processing Batch: {batch_name} ({len(account_dirs)} accounts)")

        for account_dir in account_dirs:
            handle = account_dir.name
            site_dir = account_dir / "site"
            data_dir = account_dir / f"{handle}_data"
            backups_dir = account_dir / "backups"

            acc_files = 0
            acc_bytes = 0

            # 1. Upload site files (HTML, CSS, assets)
            if site_dir.is_dir():
                f_count, b_count = upload_directory_to_r2(s3, bucket, site_dir, f"{batch_name}/{handle}/site")
                acc_files += f_count
                acc_bytes += b_count

            # 2. Upload scraped media/profile data
            if data_dir.is_dir():
                f_count, b_count = upload_directory_to_r2(s3, bucket, data_dir, f"{batch_name}/{handle}/media")
                acc_files += f_count
                acc_bytes += b_count

            # 3. Upload backups (if any)
            if backups_dir.is_dir():
                f_count, b_count = upload_directory_to_r2(s3, bucket, backups_dir, f"{batch_name}/{handle}/backups")
                acc_files += f_count
                acc_bytes += b_count

            if acc_files > 0:
                accounts_processed += 1
                total_files += acc_files
                total_bytes += acc_bytes
                size_mb = acc_bytes / (1024 * 1024)
                print(f"  ✓ @{handle:<24} {acc_files:>3} files ({size_mb:.2f} MB)")

                # Update site_path in database to point to cloud preview
                if db and site_dir.is_dir():
                    preview_url = get_preview_url(batch_name, handle, "index.html")
                    if preview_url:
                        try:
                            db.execute(
                                "UPDATE leads SET site_path=?, updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",
                                (preview_url, batch_name, handle),
                            )
                        except Exception as exc:
                            print(f"    (DB update skipped for @{handle}: {exc})")
            else:
                print(f"  - @{handle:<24} (no files to upload)")

    total_mb = total_bytes / (1024 * 1024)
    print("\n" + "=" * 60)
    print("🎉 R2 Upload Migration Complete!")
    print(f"• Accounts migrated: {accounts_processed}")
    print(f"• Total files uploaded: {total_files}")
    print(f"• Total volume transferred: {total_mb:.2f} MB")
    if is_d1_configured():
        print("• Database lead records synced to Cloudflare D1 with R2 preview links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
