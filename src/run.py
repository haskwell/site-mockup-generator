#!/usr/bin/env python3
"""Build sites for the accounts listed in config/accounts.txt."""

from __future__ import annotations

import glob
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path
from src.pipeline_common import Logger, MODEL, MIN_SIZE, TIMEOUT_SECONDS, account_handle, find_agy, get_venv_python, run_streaming
from src.r2_storage import is_r2_configured, upload_lead_assets, upload_lead_media, upload_site


REPO = Path(__file__).resolve().parents[1]


def parse_revision_sections(content: str, accounts: set[str]) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in content.splitlines():
        match = re.match(r"^#[ \t]+(\S+)\s*$", line)
        if match:
            candidate = match.group(1)
            current = candidate if candidate in accounts else None
            if current is not None:
                sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return {user: "\n".join(lines).strip() for user, lines in sections.items()}


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
            if tag in {"img", "script", "source"} and attrs.get("src"):
                self.refs.append(attrs["src"])
            if tag == "img" and attrs.get("srcset"):
                self.refs.extend(candidate.strip().split()[0] for candidate in attrs["srcset"].split(",") if candidate.strip())
            if tag == "video" and attrs.get("poster"):
                self.refs.append(attrs["poster"])
            if tag == "link" and attrs.get("href") and attrs.get("rel") in {"stylesheet", "icon"}:
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
        if ref.startswith(("https://", "http://", "data:", "#")):
            continue
        target = (site / ref.split("?", 1)[0].split("#", 1)[0]).resolve()
        if not target.is_relative_to(site.resolve()) or not target.is_file():
            errors.append(f"missing or unsafe referenced file: {ref}")
    return errors


def parse_users(path: Path) -> list[str]:
    users, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw:
            continue
        try:
            username = account_handle(raw)
        except ValueError as exc:
            print(f"Skipping account entry {raw!r}: {exc}", file=sys.stderr)
            continue
        if username.casefold() not in seen:
            users.append(username)
            seen.add(username.casefold())
    return users


def process_account(user: str, root: Path, python: str, force: bool, logger: Logger,
                    *, emit=None, options: dict | None = None, cancel_event=None) -> int:
    options = options or {}
    def status(value: str, line: str = ""):
        if emit:
            emit(user, value, line)
    status("scraping", "Starting profile scrape")
    account = root / user
    data = account / f"{user}_data"
    site = account / "site"
    scrape_only = options.get("scrape_only")
    import datetime as dt
    try:
        (account / "logs").mkdir(parents=True, exist_ok=True)
        if not scrape_only:
            (site / "assets").mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "prompts/SKILL.md", account / "SKILL.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to prepare account files: {exc}")
        return 1

    index = site / "index.html"
    if not force and not options.get("scrape_only") and index.is_file() and index.stat().st_size >= MIN_SIZE:
        logger.log("INFO", f"{user}: site already built, skipping (use FORCE=1 to rebuild)")
        return 2

    backup = account / "backups" / f"site_before_build_{dt.datetime.now():%Y%m%d_%H%M%S}"
    if not scrape_only and site.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(site, backup)
    agy_log = account / "logs" / f"agy_{dt.datetime.now():%Y-%m-%d_%H%M}.log"

    python_bin = os.environ.get("PIPELINE_PYTHON") or python
    logger.log("INFO", f"{user}: scraping...")
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
        logger.log("ERROR", f"{user}: scraper failed")
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
            logger.log("ERROR", f"{user}: profile summary extraction failed")
            return 1
        rc, _ = run_streaming(sheet_command, REPO, logger, cancel_event=cancel_event)
        if rc:
            status("failed", "Google Sheets update failed")
            logger.log("ERROR", f"{user}: Google Sheets update failed")
            return 1
        if is_r2_configured():
            logger.log("INFO", f"{user}: syncing scraped media to Cloudflare R2...")
            upload_lead_media(account, root.name, user)
        status("scraped", "Scrape complete; added to Google Sheet")
        return 0
    agy_bin = find_agy()
    if agy_bin is None:
        message = "agy executable not found on PATH or at ~/.local/bin/agy"
        logger.log("ERROR", f"{user}: {message}")
        status("failed", message)
        return 1
    if not (data / "profile_data.json").is_file():
        logger.log("ERROR", f"{user}: no profile_data.json")
        return 1
    steps = [] if options.get("preserve_summary") and (data / "business_data.json").is_file() else [([python_bin, str(REPO / "src/profile_summary.py"), str(data / "profile_data.json"), str(data / "business_data.json")], "profile summary extraction failed")]
    for command, error in steps:
        rc, _ = run_streaming(command, REPO, logger, cancel_event=cancel_event)
        if rc:
            status("failed", error)
            logger.log("ERROR", f"{user}: {error}")
            return 1
    try:
        if force and site.exists():
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
        shutil.copy2(REPO / "prompts/GEMINI.md", account / "GEMINI.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to prepare site: {exc}")
        restore_backup(site, backup)
        return 1

    rc, _ = run_streaming([python_bin, str(REPO / "src/design.py"), user, "--output", str(account / "DESIGN.md")], REPO, logger, cancel_event=cancel_event)
    if rc:
        logger.log("ERROR", f"{user}: design direction generation failed")
        restore_backup(site, backup)
        return 1
    # DESIGN.md stays beside the project instructions and is not deployed.

    model = options.get("model", MODEL)
    logger.log("INFO", f"{user}: building site with agy ({model})...")
    status("building", "Building site with agy")
    rc, timed_out = run_streaming(
        [agy_bin, "-p", "Read GEMINI.md, DESIGN.md and SKILL.md, then build the site. DESIGN.md is binding.",
         "--model", model, "--dangerously-skip-permissions"],
        account, logger, agy_log, int(options.get("timeout", TIMEOUT_SECONDS)), cancel_event=cancel_event)
    if timed_out:
        logger.log("ERROR", f"{user}: agy timed out after 900s; build failed (see {agy_log})")
        restore_backup(site, backup)
        return 1
    if rc:
        logger.log("ERROR", f"{user}: agy exited with status {rc}; build failed (see {agy_log})")
        restore_backup(site, backup)
        return 1
    errors = validate_site(site)
    if errors:
        logger.log("ERROR", f"{user}: generated site failed validation: {'; '.join(errors)}")
        if backup.exists():
            restore_backup(site, backup)
        return 1
    size = index.stat().st_size
    logger.log("SUCCESS", f"{user}: done -> {index} ({size} bytes)")
    if is_r2_configured():
        logger.log("INFO", f"{user}: syncing site and lead assets to Cloudflare R2...")
        preview_url = upload_lead_assets(account, root.name, user)
        if preview_url:
            logger.log("SUCCESS", f"{user}: published to R2 -> {preview_url}")
    status("done", f"Built {index}")
    rc, _ = run_streaming(sheet_command, REPO, logger) if options.get("sync_sheet", True) else (0, False)
    if rc:
        logger.log("WARN", f"{user}: Google Sheets update failed; site build succeeded")
    return 0


def restore_backup(site: Path, backup: Path) -> None:
    if backup.exists():
        shutil.rmtree(site, ignore_errors=True)
        shutil.copytree(backup, site)


def main() -> int:
    import datetime as dt
    log_dir = REPO / "logs"
    log_dir.mkdir(exist_ok=True)
    session_log = log_dir / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_run_{os.getpid()}.log"
    logger = Logger(session_log)
    try:
        root = Path(os.environ.get("WEBSITES_ROOT", str(Path.home() / "websites" / f"{dt.date.today():%Y-%m-%d}")))
        accounts = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "config/accounts.txt"
        if not accounts.is_file():
            logger.log("ERROR", f"Accounts file not found: {accounts}")
            return 1
        root.mkdir(parents=True, exist_ok=True)
        if not (REPO / "config/auth.json").is_file():
            logger.log("WARN", "config/auth.json not found; Instagram scraping will run without a saved login session")
        users = parse_users(accounts)
        if not users:
            logger.log("ERROR", f"No accounts found in {accounts}")
            return 1
        python = os.environ.get("PIPELINE_PYTHON") or get_venv_python(REPO)
        ok, skipped, failed = [], [], []
        for i, user in enumerate(users, 1):
            logger.log("INFO", f"=== [{i}/{len(users)}] @{user} ===")
            rc = process_account(user, root, python, os.environ.get("FORCE", "0") == "1", logger)
            (ok if rc == 0 else skipped if rc == 2 else failed).append(user)
            if i < len(users) and rc != 2:
                delay = random.randint(20, 60)
                logger.log("INFO", f"Waiting {delay}s before the next account...")
                time.sleep(delay)
        revisions = REPO / "config/REVISIONS.md"
        previous = revisions.read_text(encoding="utf-8") if revisions.exists() else ""
        valid_users = set(users)
        old_sections = parse_revision_sections(previous, valid_users)
        headings = "".join(f"# {user}\n\n" for user in ok + skipped if user not in old_sections)
        revisions.write_text(previous.rstrip() + ("\n\n" if previous.strip() and headings else "") + headings, encoding="utf-8")
        logger.log("INFO", f"Preserved existing revision notes in {revisions}")
        print("\n================ Summary ================")
        print(f"Built:   {len(ok)}  {' '.join(ok)}")
        print(f"Skipped: {len(skipped)}  {' '.join(skipped)}")
        print(f"Failed:  {len(failed)}  {' '.join(failed)}")
        print(f"Output:  {root}/<username>/site/index.html")
        return 1 if failed else 0
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
