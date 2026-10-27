"""Cloudflare R2 (S3-compatible) storage manager for mockups and media assets."""
from __future__ import annotations

import json
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


_cached_s3_client = None
_cached_s3_creds = None


def get_s3_client():
    """Create and return a boto3 S3 client configured for Cloudflare R2, cached for reuse."""
    global _cached_s3_client, _cached_s3_creds
    import boto3
    from botocore.config import Config

    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    access_key = os.environ["R2_ACCESS_KEY_ID"].strip()
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"].strip()
    creds_tuple = (account_id, access_key, secret_key)

    if _cached_s3_client is not None and _cached_s3_creds == creds_tuple:
        return _cached_s3_client

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )
    _cached_s3_client = client
    _cached_s3_creds = creds_tuple
    return client


def has_r2_site(batch: str, handle: str) -> bool:
    """Return True if the site index.html exists in R2 for this lead."""
    if not is_r2_configured():
        return False
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    key = f"{batch}/{handle}/site/index.html"
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def get_r2_object(key: str) -> tuple[bytes, str] | None:
    """Fetch raw object bytes and Content-Type from R2."""
    if not is_r2_configured():
        return None
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        body = resp["Body"].read()
        ct = resp.get("ContentType") or guess_content_type(Path(key))
        return body, ct
    except Exception:
        return None


def get_r2_mtime(key: str) -> float | None:
    """Return the LastModified epoch timestamp of an object in R2."""
    if not is_r2_configured():
        return None
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
        dt_val = resp.get("LastModified")
        return dt_val.timestamp() if dt_val else None
    except Exception:
        return None


def get_preview_url(batch: str, handle: str, path: str = "index.html", verify_exists: bool = False) -> str | None:
    """Return the private preview URL path (/preview/{batch}/{handle}/{clean_path})."""
    if not is_r2_configured():
        return None
    if verify_exists and not has_r2_site(batch, handle):
        return None
    clean_path = path.lstrip("/")
    return f"/preview/{batch}/{handle}/{clean_path}"


def get_presigned_recording_url(
    batch: str, handle: str, filename: str, expires_in: int = 3600, download: bool = False
) -> str | None:
    """Generate a temporary signed URL for direct R2 streaming or download."""
    if not is_r2_configured():
        return None
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    key = f"{batch}/{handle}/recordings/{filename}"
    params: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if download:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )
    except Exception:
        return None


def get_recording_url(batch: str, handle: str, filename: str) -> str | None:
    """Compatibility alias for generating presigned recording URL."""
    return get_presigned_recording_url(batch, handle, filename)


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
    name_parts = filename.rsplit(".", 1)[0].split("-")
    screen = name_parts[-1] if len(name_parts) > 1 else "desktop"
    return f"/api/lead/{handle}/recording/{screen}"


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


def delete_recording(batch: str, handle: str, screen: str | None = None) -> int:
    """Delete recording(s) from R2 for a lead. If screen is provided, only deletes that screen's recording."""
    if not is_r2_configured():
        return 0
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    prefix = f"{batch}/{handle}/recordings/"
    paginator = s3.get_paginator("list_objects_v2")
    deleted_count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = []
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key[len(prefix):]
            if screen and screen != "all":
                if f"-{screen}." in filename or filename.startswith(f"{handle}-{screen}.") or filename.startswith(f"{screen}."):
                    objects.append({"Key": key})
            else:
                objects.append({"Key": key})
        if objects:
            resp = s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            if isinstance(resp, dict) and resp.get("Errors"):
                err_msg = "; ".join(str(e.get("Message") or e.get("Code") or e) for e in resp["Errors"])
                raise RuntimeError(f"R2 delete_objects failed: {err_msg}")
            deleted_count += len(objects)
    return deleted_count


def get_lead_json(batch: str, handle: str, filename: str) -> Any:
    """Fetch and parse a JSON file from R2 (e.g. profile_data.json or business_data.json)."""
    if not is_r2_configured():
        return None
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    for key in [
        f"{batch}/{handle}/media/{filename}",
        f"{batch}/{handle}/{filename}",
        f"{batch}/{handle}/site/{filename}",
    ]:
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(resp["Body"].read().decode("utf-8"))
        except Exception:
            continue
    return None


def get_lead_text(batch: str, handle: str, filename: str) -> str | None:
    """Fetch text content of a file from R2 (e.g. DESIGN.md)."""
    if not is_r2_configured():
        return None
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    keys_to_try = [
        f"{batch}/{handle}/site/{filename}",
        f"{batch}/{handle}/{filename}",
        f"{batch}/{handle}/media/{filename}",
        f"{batch}/{handle}/site/{filename.lower()}",
        f"{batch}/{handle}/{filename.lower()}",
        f"{batch}/{handle}/media/{filename.lower()}",
    ]
    for key in keys_to_try:
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except Exception:
            continue
    return None


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
                key = obj["Key"]
                rel_path = key[len(prefix):]
                if not rel_path or rel_path.endswith("/"):
                    continue
                target_path = dest_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                resp = s3.get_object(Bucket=bucket, Key=key)
                with target_path.open("wb") as f:
                    f.write(resp["Body"].read())
                found_any = True
    except Exception:
        return False
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
    try:
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel_path = key[len(prefix):]
                if not rel_path or rel_path.endswith("/"):
                    continue
                target_path = dest_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                resp = s3.get_object(Bucket=bucket, Key=key)
                with target_path.open("wb") as f:
                    f.write(resp["Body"].read())
                found_any = True
    except Exception:
        return False

    return found_any


def upload_lead_media(account_dir: Path, batch: str, handle: str) -> int:
    """Upload scraped data directory {handle}_data/ to {batch}/{handle}/media in R2."""
    if not is_r2_configured():
        return 0
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    data_dir = account_dir / f"{handle}_data"
    if not data_dir.is_dir():
        return 0
    uploaded = 0
    for item in data_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(data_dir).as_posix()
            r2_key = f"{batch}/{handle}/media/{rel_path}"
            ct = guess_content_type(item)
            with item.open("rb") as f:
                s3.put_object(Bucket=bucket, Key=r2_key, Body=f, ContentType=ct)
            uploaded += 1
    return uploaded


def upload_lead_assets(account_dir: Path, batch: str, handle: str) -> str | None:
    """Upload all lead assets (site/, DESIGN.md, selected_posts.json, media) to R2."""
    if not is_r2_configured():
        return None

    site_dir = account_dir / "site"
    preview_url = upload_site(site_dir, batch, handle) if site_dir.is_dir() else None

    # Upload DESIGN.md
    design_file = account_dir / "DESIGN.md"
    if design_file.is_file():
        upload_file(design_file, f"{batch}/{handle}/DESIGN.md", "text/markdown")

    # Upload selected_posts.json
    selected_file = account_dir / "selected_posts.json"
    if selected_file.is_file():
        upload_file(selected_file, f"{batch}/{handle}/selected_posts.json", "application/json")

    # Upload scraped media and profile data
    data_dir = account_dir / f"{handle}_data"
    if data_dir.is_dir():
        expected = sum(1 for item in data_dir.rglob("*") if item.is_file())
        uploaded = upload_lead_media(account_dir, batch, handle)
        if uploaded < expected:
            raise RuntimeError(f"partial R2 media upload ({uploaded}/{expected} files)")

    return preview_url


def delete_site_assets(batch: str, handle: str) -> int:
    """Delete only generated site files under {batch}/{handle}/site/ from R2."""
    if not is_r2_configured():
        return 0

    bucket = os.environ["R2_BUCKET_NAME"].strip()
    s3 = get_s3_client()
    prefix = f"{batch}/{handle}/site/"

    paginator = s3.get_paginator("list_objects_v2")
    deleted_count = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            deleted_count += len(objects)

    return deleted_count


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
