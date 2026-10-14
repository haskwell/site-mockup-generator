#!/usr/bin/env python3
"""Build sites for the accounts listed in config/accounts.txt."""

from __future__ import annotations

import datetime as dt
import glob
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO = Path(__file__).resolve().parent
MODEL = "gemini-3.8-flash-medium"
MIN_SIZE = 600


class Logger:
    def __init__(self, path: Path):
        self.file = path.open("a", encoding="utf-8")
        self.color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.colors = {"INFO": "\033[36m", "SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m"}

    def log(self, level: str, message: str) -> None:
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = self.colors.get(level, self.colors["INFO"]) if self.color else ""
        reset = "\033[0m" if self.color else ""
        line = f"{stamp} {color}{level:<8}{reset} {message}"
        print(line, flush=True)
        self.file.write(re.sub(r"\033\[[0-9;]*m", "", line) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def command_output(command: list[str], cwd: Path, logger: Logger | None = None,
                   agy_log: Path | None = None, timeout: int | None = None,
                   prefix: str = "") -> tuple[int, bool]:
    """Run a command, forwarding output and optionally recording detailed output."""
    try:
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace")
        log_file = agy_log.open("w", encoding="utf-8") if agy_log else None
        try:
            try:
                output, _ = process.communicate(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
                timed_out = True
            for line in output.splitlines():
                if log_file:
                    log_file.write(line + "\n")
                    log_file.flush()
                if logger:
                    logger.log("INFO", prefix + line)
                else:
                    print(line, flush=True)
            return (124 if timed_out else process.returncode), timed_out
        finally:
            if log_file:
                log_file.close()
    except OSError as exc:
        if logger:
            logger.log("ERROR", f"Could not run {command[0]}: {exc}")
        else:
            print(f"ERROR: Could not run {command[0]}: {exc}", file=sys.stderr)
        return 127, False


def parse_users(path: Path) -> list[str]:
    users = []
    for line in path.read_text(encoding="utf-8").splitlines():
        username = line.split("#", 1)[0].replace("\r", "").lstrip(" \t\n\v\f@").rstrip()
        if username:
            users.append(username)
    return users


def process_account(user: str, root: Path, python: str, force: bool, logger: Logger) -> int:
    account = root / user
    data = account / f"{user}_data"
    site = account / "site"
    agy_log = account / "logs" / f"agy_{dt.datetime.now():%Y-%m-%d_%H%M}.log"
    try:
        (account / "logs").mkdir(parents=True, exist_ok=True)
        (site / "assets").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "prompts/SKILL.md", account / "SKILL.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to prepare account files: {exc}")
        return 1

    index = site / "index.html"
    if not force and index.is_file() and index.stat().st_size >= MIN_SIZE:
        logger.log("INFO", f"{user}: site already built, skipping (use FORCE=1 to rebuild)")
        return 2

    python_bin = os.environ.get("PIPELINE_PYTHON") or python
    logger.log("INFO", f"{user}: scraping...")
    rc, _ = command_output([python_bin, str(REPO / "src/scraper.py"), user, "--captions", "--auth", str(REPO / "config/auth.json")], account)
    if rc:
        logger.log("ERROR", f"{user}: scraper failed")
        return 1
    if not (data / "profile_data.json").is_file():
        logger.log("ERROR", f"{user}: no profile_data.json")
        return 1
    steps = [
        ([python_bin, str(REPO / "src/profile_summary.py"), str(data / "profile_data.json"), str(data / "business_data.json")], "profile summary extraction failed"),
        ([python_bin, str(REPO / "src/update_sheet.py"), str(data / "business_data.json")], "Google Sheets update failed; see the error above"),
    ]
    for command, error in steps:
        rc, _ = command_output(command, REPO)
        if rc:
            logger.log("ERROR", f"{user}: {error}")
            return 1
    try:
        images = glob.glob(str(data / "posts/web/*.webp"))
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
  <link rel="icon" href="assets/pfp.jpg">
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
        return 1

    rc, _ = command_output([python_bin, str(REPO / "src/design.py"), user, "--output", str(account / "DESIGN.md")], REPO)
    if rc:
        logger.log("ERROR", f"{user}: design direction generation failed")
        return 1
    try:
        shutil.copy2(account / "DESIGN.md", site / "DESIGN.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to copy DESIGN.md into the site directory: {exc}")
        return 1

    logger.log("INFO", f"{user}: building site with agy ({MODEL})...")
    rc, timed_out = command_output(
        ["agy", "-p", "Read GEMINI.md, DESIGN.md and SKILL.md, then build the site. DESIGN.md is binding.",
         "--model", MODEL, "--dangerously-skip-permissions"],
        account, logger, agy_log, 900)
    if timed_out:
        logger.log("ERROR", f"{user}: agy timed out after 900s; build failed (see {agy_log})")
        return 1
    if rc:
        logger.log("ERROR", f"{user}: agy exited with status {rc}; build failed (see {agy_log})")
        return 1
    size = index.stat().st_size if index.exists() else 0
    if size < MIN_SIZE:
        logger.log("ERROR", f"{user}: agy did not fill in index.html (see {agy_log})")
        return 1
    logger.log("SUCCESS", f"{user}: done -> {index} ({size} bytes)")
    return 0


def main() -> int:
    log_dir = REPO / "logs"
    log_dir.mkdir(exist_ok=True)
    session_log = log_dir / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_run_{os.getpid()}.log"
    logger = Logger(session_log)
    try:
        root = Path(os.environ.get("WEBSITES_ROOT", f"/home/frost/websites/{dt.date.today():%Y-%m-%d}"))
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
        python = str(REPO / ".venv/bin/python") if (REPO / ".venv/bin/python").is_file() and not os.environ.get("PIPELINE_PYTHON") else os.environ.get("PIPELINE_PYTHON", "python3")
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
        revisions.write_text("".join(f"# {user}\n\n" for user in ok + skipped), encoding="utf-8")
        logger.log("INFO", f"Prepared {revisions} with headings for built and skipped sites")
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
