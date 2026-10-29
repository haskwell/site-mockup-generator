#!/usr/bin/env python3
"""Site revision workflow for the dashboard application."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from src.core.common import (
    Logger,
    MODEL,
    MIN_SIZE,
    TIMEOUT_SECONDS,
    find_agy,
    get_asset_path,
    run_streaming,
    REPO_ROOT,
)
from src.storage.r2 import download_site, get_lead_text, get_r2_mtime, is_r2_configured, upload_file, upload_site
from src.pipeline.builder import validate_site

REPO = REPO_ROOT


def revise(user: str, revision: str, root: Path, accounts: set[str] | None = None, logger: Logger | Any = None,
           *, emit=None, model: str = MODEL, timeout: int = TIMEOUT_SECONDS,
           cancel_event=None) -> int:
    def report(status: str, line: str = ""):
        if emit: emit(user, status, line)
    def log(level: str, msg: str):
        if logger is not None and hasattr(logger, "log"):
            logger.log(level, msg)
        elif emit:
            emit(user, "log", f"{level}: {msg}")
    if not revision.strip():
        return 2
    if accounts is not None and user not in accounts:
        log("ERROR", f"Unknown account heading '#{user}'; skipping")
        return 1
    account = root / user
    site_index = account / "site/index.html"
    if is_r2_configured():
        r2_mtime = get_r2_mtime(f"{root.name}/{user}/site/index.html")
        if not site_index.is_file() or (r2_mtime is not None and r2_mtime > site_index.stat().st_mtime):
            log("INFO", f"{user}: pulling latest site files from Cloudflare R2 for revision...")
            download_site(root.name, user, account / "site")
            if r2_mtime is not None and site_index.is_file():
                try:
                    os.utime(site_index, (r2_mtime, r2_mtime))
                except Exception:
                    pass
    if not site_index.is_file():
        log("ERROR", f"{user}: existing site not found at {site_index}")
        return 1
    design_file = account / "DESIGN.md"
    if not design_file.is_file() and (account / "site/DESIGN.md").is_file():
        design_file = account / "site/DESIGN.md"
    if is_r2_configured():
        r2_design_mtime = get_r2_mtime(f"{root.name}/{user}/site/DESIGN.md") or get_r2_mtime(f"{root.name}/{user}/DESIGN.md")
        if not design_file.is_file() or (r2_design_mtime is not None and r2_design_mtime > design_file.stat().st_mtime):
            cloud_design = get_lead_text(root.name, user, "DESIGN.md")
            if cloud_design:
                account.mkdir(parents=True, exist_ok=True)
                design_file.write_text(cloud_design, encoding="utf-8")
                if r2_design_mtime is not None:
                    try:
                        os.utime(design_file, (r2_design_mtime, r2_design_mtime))
                    except Exception:
                        pass
                log("INFO", f"{user}: fetched latest DESIGN.md from Cloudflare R2")
    if not design_file.is_file():
        try:
            design_file.write_text(f"# Design Direction for {user}\nClean, modern, responsive website.\n", encoding="utf-8")
            log("WARN", f"{user}: DESIGN.md missing; created fallback design direction")
        except Exception:
            log("ERROR", f"{user}: DESIGN.md not found in {account}")
            return 1
    agy_bin = find_agy()
    if not agy_bin:
        message = "agy executable not found on PATH or at ~/.local/bin/agy"
        log("ERROR", f"{user}: {message}")
        report("failed", message)
        return 1
    try:
        (account / "logs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(get_asset_path("prompts/GEMINI.md"), account / "GEMINI.md")
        shutil.copy2(get_asset_path("prompts/SKILL.md"), account / "SKILL.md")
    except OSError as exc:
        log("ERROR", f"{user}: failed to copy generation instructions: {exc}")
        return 1

    agy_log = account / "logs" / f"agy_revision_{dt.datetime.now():%Y-%m-%d_%H%M%S}_{time.monotonic_ns() % 1000000}.log"
    backup = account / "backups" / f"site_before_revision_{dt.datetime.now():%Y%m%d_%H%M%S}_{time.monotonic_ns() % 1000000}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(account / "site", backup)
    prompt = ("Revise the existing website in site/ to address these requested changes. "
              "Preserve its working content and assets unless a requested change requires updating them.\n\n"
              "Revision requests:\n" + revision)
    log("INFO", f"{user}: revising site with agy ({model})...")
    report("building", "Applying revision")
    # NOTE: --dangerously-skip-permissions is used for automated revisions; revision requests and scraped data are untrusted user input.
    code, timed_out = run_streaming([agy_bin, "-p", prompt, "--model", model,
                                     "--dangerously-skip-permissions"],
                                    account, logger, agy_log, timeout, f"{user}: ",
                                    cancel_event=cancel_event)
    if timed_out:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        log("ERROR", f"{user}: agy timed out after {timeout}s; revision failed (see {agy_log})")
        report("failed", "agy timed out")
        return 1
    if code:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        log("ERROR", f"{user}: agy exited with status {code}; revision failed (see {agy_log})")
        report("failed", f"agy exited with status {code}")
        return 1
    size = site_index.stat().st_size if site_index.is_file() else 0
    if not site_index.is_file() or size < MIN_SIZE:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        log("ERROR", f"{user}: index.html is missing or smaller than {MIN_SIZE} bytes after revision (see {agy_log})")
        report("failed", f"index.html is missing or smaller than {MIN_SIZE} bytes")
        return 1
    errors = validate_site(account / "site")
    if errors:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        log("ERROR", f"{user}: revised site failed validation: {'; '.join(errors)}")
        report("failed", "; ".join(errors))
        return 1
    log("SUCCESS", f"{user}: revision complete -> {site_index} ({size} bytes)")
    if is_r2_configured():
        log("INFO", f"{user}: uploading revised site to Cloudflare R2...")
        upload_site(account / "site", root.name, user)
        if design_file.is_file():
            upload_file(design_file, f"{root.name}/{user}/DESIGN.md", "text/markdown")
    report("done", f"Revision complete: {size} bytes")
    return 0

