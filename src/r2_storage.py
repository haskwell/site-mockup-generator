"""Cloudflare R2 (S3-compatible) storage manager for mockups and media assets."""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")

# Fallback MIME mappings to ensure reliable Content-Type across all platforms (Windows/Linux)
MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".zip": "application/zip",
}


def guess_content_type(file_path: Path) -> str:
    """Guess MIME type with built-in fallbacks."""
    suffix = file_path.suffix.lower()
    if suffix in MIME_OVERRIDES:
        return MIME_OVERRIDES[suffix]
    guessed, _ = mimetypes.guess_type(str(file_path))
    return guessed or "application/octet-stream"


def is_r2_configured() -> bool:
    """Return True if Cloudflare R2 credentials are set."""
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("R2_BUCKET_NAME", "").strip()
    return bool(account_id and access_key and secret_key and bucket)


def get_s3_client():
    """Create and return a boto3 S3 client configured for Cloudflare R2."""
    import boto3
    from botocore.config import Config

    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    access_key = os.environ["R2_ACCESS_KEY_ID"].strip()
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"].strip()
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def get_preview_url(batch: str, handle: str, path: str = "index.html") -> str | None:
    """Return the public CDN preview URL for a given mockup, if configured."""
    public_base = os.environ.get("R2_PUBLIC_URL", "").strip().rstrip("/")
    if not public_base:
        return None
    clean_path = path.lstrip("/")
    return f"{public_base}/{batch}/{handle}/site/{clean_path}"


def get_recording_url(batch: str, handle: str, filename: str) -> str | None:
    """Return the public CDN URL for a given recording video, if configured."""
    public_base = os.environ.get("R2_PUBLIC_URL", "").strip().rstrip("/")
    if not public_base:
        return None
    clean_filename = filename.lstrip("/")
    return f"{public_base}/{batch}/{handle}/recordings/{clean_filename}"


def upload_recording(local_path: Path, batch: str, handle: str, filename: str) -> str | None:
    """Upload a recorded video to R2 under {batch}/{handle}/recordings/{filename}."""
    if not is_r2_configured() or not local_path.is_file():
        return None
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    r2_key = f"{batch}/{handle}/recordings/{filename}"
    ct = guess_content_type(local_path)
    with local_path.open("rb") as f:
        s3.put_object(Bucket=bucket, Key=r2_key, Body=f, ContentType=ct)
    return get_recording_url(batch, handle, filename)


def list_recordings(batch: str, handle: str) -> list[str]:
    """List all recording filenames stored in R2 for a lead."""
    if not is_r2_configured():
        return []
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    prefix = f"{batch}/{handle}/recordings/"
    paginator = s3.get_paginator("list_objects_v2")
    filenames: list[str] = []
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                name = key[len(prefix):]
                if name and not name.endswith("/"):
                    filenames.append(name)
    except Exception:
        pass
    return filenames


def download_recording(batch: str, handle: str, filename: str, dest_path: Path) -> bool:
    """Download a recording video from R2 to dest_path."""
    if not is_r2_configured():
        return False
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    key = f"{batch}/{handle}/recordings/{filename}"
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with dest_path.open("wb") as f:
            f.write(resp["Body"].read())
        return True
    except Exception:
        return False


def download_lead_folder(batch: str, handle: str, dest_dir: Path) -> bool:
    """Download all files for an account from R2 into a local directory."""
    if not is_r2_configured():
        return False
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    prefix = f"{batch}/{handle}/"
    paginator = s3.get_paginator("list_objects_v2")
    found_any = False
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                found_any = True
                key = obj["Key"]
                rel_path = key[len(prefix):]
                if not rel_path or rel_path.endswith("/"):
                    continue
                target_path = dest_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                resp = s3.get_object(Bucket=bucket, Key=key)
                with target_path.open("wb") as f:
                    f.write(resp["Body"].read())
    except Exception:
        pass
    return found_any


def upload_file(local_path: Path, r2_key: str, content_type: str | None = None) -> bool:
    """Upload a single local file to Cloudflare R2."""
    if not is_r2_configured() or not local_path.is_file():
        return False
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    ct = content_type or guess_content_type(local_path)
    with local_path.open("rb") as f:
        s3.put_object(Bucket=bucket, Key=r2_key, Body=f, ContentType=ct)
    return True


def upload_site(local_site_dir: Path, batch: str, handle: str) -> str | None:
    """Upload an entire site directory to R2, returning the preview URL."""
    if not is_r2_configured() or not local_site_dir.is_dir():
        return None

    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()

    for item in local_site_dir.rglob("*"):
        if item.is_file():
            # Use as_posix() to guarantee forward slashes on Windows
            rel_path = item.relative_to(local_site_dir).as_posix()
            r2_key = f"{batch}/{handle}/site/{rel_path}"
            ct = guess_content_type(item)
            with item.open("rb") as f:
                s3.put_object(Bucket=bucket, Key=r2_key, Body=f, ContentType=ct)

    return get_preview_url(batch, handle, "index.html")


def download_site(batch: str, handle: str, dest_dir: Path) -> bool:
    """Download all site files for an account from R2 into a local directory."""
    if not is_r2_configured():
        return False

    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    prefix = f"{batch}/{handle}/site/"

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    found_any = False
    for page in pages:
        for obj in page.get("Contents", []):
            found_any = True
            key = obj["Key"]
            rel_path = key[len(prefix):]
            if not rel_path or rel_path.endswith("/"):
                continue
            target_path = dest_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            resp = s3.get_object(Bucket=bucket, Key=key)
            with target_path.open("wb") as f:
                f.write(resp["Body"].read())

    return found_any


def delete_lead_assets(batch: str, handle: str) -> int:
    """Delete all files under {batch}/{handle}/ from R2 (e.g. when lead is marked lost)."""
    if not is_r2_configured():
        return 0

    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    prefix = f"{batch}/{handle}/"

    paginator = s3.get_paginator("list_objects_v2")
    deleted_count = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted_count += len(objects)

    return deleted_count
