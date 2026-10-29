#!/usr/bin/env python3
"""Site building and validation pipeline for the dashboard application."""

from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from src.core.common import (
    Logger,
    MODEL,
    MIN_SIZE,
    TIMEOUT_SECONDS,
    account_handle,
    find_agy,
    get_asset_path,
    get_venv_python,
    run_streaming,
    REPO_ROOT,
)
from src.storage.r2 import is_r2_configured, upload_lead_assets, upload_lead_media, upload_site


REPO = REPO_ROOT


def validate_site(site: Path) -> list[str]:
    from html.parser import HTMLParser
    index = site / "index.html"
    if not index.is_file() or index.stat().st_size < MIN_SIZE:
        return [f"index.html missing or smaller than {MIN_SIZE} bytes"]
    class Checker(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.refs: list[str] = []
            self.errors: list[str] = []
            self.tags: set[str] = set()
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag in {"html", "head", "body"}:
                self.tags.add(tag)
            if tag in {"img", "script", "source", "video"} and attrs.get("src"):
                self.refs.append(attrs["src"])
            if tag == "img" and attrs.get("srcset"):
                self.refs.extend(candidate.strip().split()[0] for candidate in attrs["srcset"].split(",") if candidate.strip())
            if tag == "video" and attrs.get("poster"):
                self.refs.append(attrs["poster"])
            if tag == "link" and attrs.get("href"):
                rel_parts = set((attrs.get("rel") or "").lower().split())
                if rel_parts & {"stylesheet", "icon"}:
                    self.refs.append(attrs["href"])
        def error(self, message):
            self.errors.append(message)
    checker = Checker()
    try:
        html = index.read_text(encoding="utf-8")
        if "<!doctype html>" not in html.casefold():
            checker.errors.append("HTML5 doctype is missing")
        checker.feed(html)
        checker.close()
    except Exception as exc:
        return [f"invalid HTML: {exc}"]
    errors = checker.errors
    errors.extend(f"required document tag <{tag}> is missing" for tag in {"html", "head", "body"} - checker.tags)
    for ref in checker.refs:
        if ref.startswith(("https://", "http://", "//", "data:", "#")):
            continue
        clean_ref = ref.lstrip("/").split("?", 1)[0].split("#", 1)[0]
        if not clean_ref:
            continue
        target = (site / clean_ref).resolve()
        if not target.is_relative_to(site.resolve()) or not target.is_file():
            errors.append(f"missing or unsafe referenced file: {ref}")
    import re
    for css_file in site.rglob("*.css"):
        try:
            css_text = css_file.read_text(encoding="utf-8")
            for url_ref in re.findall(r'url\s*\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', css_text):
                url_ref = url_ref.strip()
                if not url_ref.startswith(("https://", "http://", "//", "data:", "#")):
                    clean_url_ref = url_ref.lstrip("/").split("?", 1)[0].split("#", 1)[0]
                    if not clean_url_ref:
                        continue
                    base_dir = site if url_ref.startswith("/") else css_file.parent
                    target = (base_dir / clean_url_ref).resolve()
                    if not target.is_relative_to(site.resolve()) or not target.is_file():
                        errors.append(f"missing or unsafe referenced file in CSS: {url_ref}")
        except Exception:
            pass
    return errors


def process_account(user: str, root: Path, python: str, force: bool, logger: Logger | Any = None,
                    *, emit=None, options: dict | None = None, cancel_event=None) -> int:
    options = options or {}
    def status(value: str, line: str = ""):
        if emit:
            emit(user, value, line)
    def log(level: str, msg: str):
        if logger is not None and hasattr(logger, "log"):
            logger.log(level, msg)
        elif emit:
            emit(user, "log", f"{level}: {msg}")
    status("scraping", "Starting profile scrape")
    account = root / user
    data = account / f"{user}_data"
    site = account / "site"
    scrape_only = options.get("scrape_only")
    import datetime as dt
    try:
        (account / "logs").mkdir(parents=True, exist_ok=True)
        if not scrape_only:
            shutil.copy2(get_asset_path("prompts/SKILL.md"), account / "SKILL.md")
    except OSError as exc:
        log("ERROR", f"{user}: failed to prepare account files: {exc}")
        return 1

    index = site / "index.html"
    if not force and not options.get("rescrape") and not options.get("scrape_only") and index.is_file() and index.stat().st_size >= MIN_SIZE:
        log("INFO", f"{user}: site already built, skipping (use FORCE=1 to rebuild)")
        return 2

    backup = account / "backups" / f"site_before_build_{dt.datetime.now():%Y%m%d_%H%M%S}"
    if not scrape_only and site.exists() and any(site.iterdir()):
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(site, backup)
    agy_log = account / "logs" / f"agy_{dt.datetime.now():%Y-%m-%d_%H%M}.log"

    python_bin = os.environ.get("PIPELINE_PYTHON") or python
    log("INFO", f"{user}: scraping...")
    scraper_command = [python_bin, str(REPO / "src/scraper.py"), user,
                       "--max-posts", str(options.get("max_posts", 18)),
                       "--attempts", str(options.get("attempts", 3)),
                       "--auth", str(options.get("auth_path", REPO / "config/auth.json"))]
    if options.get("captions", True): scraper_command.append("--captions")
    if options.get("headed", False): scraper_command.append("--headed")
    if options.get("rescrape", False): scraper_command.append("--force")
    rc, _ = run_streaming(scraper_command, account, logger, cancel_event=cancel_event)
    if rc:
        status("failed", "Scraper failed or was cancelled")
        log("ERROR", f"{user}: scraper failed")
        return 1
    creds_opt = options.get("credentials")
    creds_file = Path(creds_opt).resolve() if creds_opt and Path(creds_opt).is_file() else (REPO / "config/creds.json").resolve()
    sheet_command = [python_bin, str(REPO / "src/update_sheet.py"), str(data / "business_data.json"),
                     "--credentials", str(creds_file),
                     "--sheet-name", str(options.get("sheet_name", "websites"))]
    if scrape_only:
        summary_command = [python_bin, str(REPO / "src/profile_summary.py"),
                           str(data / "profile_data.json"), str(data / "business_data.json")]
        rc, _ = run_streaming(summary_command, REPO, logger, cancel_event=cancel_event)
        if rc:
            status("failed", "Profile summary extraction failed")
            log("ERROR", f"{user}: profile summary extraction failed")
            return 1
        rc, _ = run_streaming(sheet_command, REPO, logger, cancel_event=cancel_event)
        if rc:
            status("failed", "Google Sheets update failed")
            log("ERROR", f"{user}: Google Sheets update failed")
            return 1
        if is_r2_configured():
            log("INFO", f"{user}: syncing scraped media to Cloudflare R2...")
            try:
                expected = sum(1 for item in data.rglob("*") if item.is_file()) if data.is_dir() else 0
                uploaded = upload_lead_media(account, root.name, user)
                if uploaded < expected or (expected == 0 and uploaded == 0):
                    raise RuntimeError(f"partial or empty R2 media upload ({uploaded}/{expected} files)")
            except Exception as exc:
                status("failed", f"R2 media sync failed: {exc}")
                log("ERROR", f"{user}: R2 media sync failed: {exc}")
                return 1
        status("scraped", "Scrape complete; added to Google Sheet")
        return 0
    agy_bin = find_agy()
    if agy_bin is None:
        message = "agy executable not found on PATH or at ~/.local/bin/agy"
        log("ERROR", f"{user}: {message}")
        status("failed", message)
        return 1
    if not (data / "profile_data.json").is_file():
        log("ERROR", f"{user}: no profile_data.json")
        return 1
    steps = [] if options.get("preserve_summary") and (data / "business_data.json").is_file() else [([python_bin, str(REPO / "src/profile_summary.py"), str(data / "profile_data.json"), str(data / "business_data.json")], "profile summary extraction failed")]
    for command, error in steps:
        rc, _ = run_streaming(command, REPO, logger, cancel_event=cancel_event)
        if rc:
            status("failed", error)
            log("ERROR", f"{user}: {error}")
            return 1
    try:
        if (force or options.get("rescrape")) and site.exists():
            shutil.rmtree(site)
        (site / "assets").mkdir(parents=True, exist_ok=True)
        images = glob.glob(str(data / "posts/web/*.webp"))
        selected = options.get("selected_photos")
        if selected is not None:
            allowed = {Path(name).name for name in selected}
            images = [image for image in images if Path(image).name in allowed]
        if not images:
            raise FileNotFoundError("no images to copy")
        for image in images:
            shutil.copy2(image, site / "assets")
        if (data / "pfp.jpg").is_file():
            shutil.copy2(data / "pfp.jpg", site / "assets/pfp.jpg")
        index.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mockup</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
</body>
</html>
""", encoding="utf-8")
        (site / "style.css").write_text("", encoding="utf-8")
        shutil.copy2(get_asset_path("prompts/GEMINI.md"), account / "GEMINI.md")
    except OSError as exc:
        log("ERROR", f"{user}: failed to prepare site: {exc}")
        restore_backup(site, backup)
        return 1

    rc, _ = run_streaming([python_bin, str(REPO / "src/design.py"), user, "--output", str(account / "DESIGN.md")], REPO, logger, cancel_event=cancel_event)
    if rc:
        log("ERROR", f"{user}: design direction generation failed")
        restore_backup(site, backup)
        return 1
    # DESIGN.md stays beside the project instructions and is not deployed.

    model = options.get("model", MODEL)
    log("INFO", f"{user}: building site with agy ({model})...")
    status("building", "Building site with agy")
    timeout_sec = int(options.get("timeout", TIMEOUT_SECONDS))
    # NOTE: --dangerously-skip-permissions is used for automated builds; scraped bios and profile text are untrusted user input.
    rc, timed_out = run_streaming(
        [agy_bin, "-p", "Read GEMINI.md, DESIGN.md and SKILL.md, then build the site. DESIGN.md is binding.",
         "--model", model, "--dangerously-skip-permissions"],
        account, logger, agy_log, timeout_sec, cancel_event=cancel_event)
    if timed_out:
        log("ERROR", f"{user}: agy timed out after {timeout_sec}s; build failed (see {agy_log})")
        restore_backup(site, backup)
        return 1
    if rc:
        log("ERROR", f"{user}: agy exited with status {rc}; build failed (see {agy_log})")
        restore_backup(site, backup)
        return 1
    errors = validate_site(site)
    if errors:
        log("ERROR", f"{user}: generated site failed validation: {'; '.join(errors)}")
        restore_backup(site, backup)
        return 1
    size = index.stat().st_size
    log("SUCCESS", f"{user}: done -> {index} ({size} bytes)")
    if is_r2_configured():
        log("INFO", f"{user}: syncing site and lead assets to Cloudflare R2...")
        try:
            preview_url = upload_lead_assets(account, root.name, user)
            if preview_url:
                log("SUCCESS", f"{user}: published to R2 -> {preview_url}")
        except Exception as exc:
            status("failed", f"R2 sync failed: {exc}")
            log("ERROR", f"{user}: R2 sync failed: {exc}")
            return 1
    status("done", f"Built {index}")
    rc, _ = run_streaming(sheet_command, REPO, logger) if options.get("sync_sheet", True) else (0, False)
    if rc:
        log("WARN", f"{user}: Google Sheets update failed; site build succeeded")
    return 0


def restore_backup(site: Path, backup: Path) -> None:
    if backup.exists():
        shutil.rmtree(site, ignore_errors=True)
        shutil.copytree(backup, site)
    else:
        # If no previous backup exists (first-time build failure), remove empty skeleton site
        shutil.rmtree(site, ignore_errors=True)

