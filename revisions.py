#!/usr/bin/env python3
"""Apply non-empty sections from config/REVISIONS.md to generated sites."""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
MODEL = "gemini-3.8-flash-medium"
TIMEOUT_SECONDS = 900
MIN_SIZE = 600


class Logger:
    def __init__(self, path: Path):
        self.file = path.open("a", encoding="utf-8")
        self.color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.colors = {"INFO": "\033[36m", "SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m"}

    def log(self, level: str, message: str) -> None:
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = self.colors[level] if self.color else ""
        reset = "\033[0m" if self.color else ""
        line = f"{stamp} {color}{level:<8}{reset} {message}"
        print(line, flush=True)
        self.file.write(re.sub(r"\033\[[0-9;]*m", "", line) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def parse_sections(path: Path) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_user: str | None = None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        match = re.match(r"^#\s*(.+)$", line)
        if match:
            if current_user is not None:
                sections.append((current_user, lines))
            current_user = match.group(1).strip()
            lines = []
        elif current_user is not None:
            lines.append(line)
    if current_user is not None:
        sections.append((current_user, lines))
    return [(user, "\n".join(lines) + "\n") for user, lines in sections]


def configured_accounts(path: Path) -> set[str]:
    users = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        user = line.split("#", 1)[0].replace("\r", "").lstrip(" \t\n\v\f@").rstrip()
        if user:
            users.add(user)
    return users


def revise(user: str, revision: str, root: Path, accounts: set[str], logger: Logger) -> int:
    if not revision.strip():
        return 2
    if user not in accounts:
        logger.log("ERROR", f"Unknown account heading '#{user}'; skipping")
        return 1
    account = root / user
    site_index = account / "site/index.html"
    if not site_index.is_file():
        logger.log("ERROR", f"{user}: existing site not found at {site_index}")
        return 1
    if not (account / "DESIGN.md").is_file():
        logger.log("ERROR", f"{user}: DESIGN.md not found in {account}")
        return 1
    try:
        (account / "logs").mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(REPO / "prompts/GEMINI.md", account / "GEMINI.md")
        shutil.copy2(REPO / "prompts/SKILL.md", account / "SKILL.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to copy generation instructions: {exc}")
        return 1

    agy_log = account / "logs" / f"agy_revision_{dt.datetime.now():%Y-%m-%d_%H%M%S}.log"
    prompt = ("Revise the existing website in site/ to address these requested changes. "
              "Preserve its working content and assets unless a requested change requires updating them.\n\n"
              "Revision requests:\n" + revision)
    logger.log("INFO", f"{user}: revising site with agy ({MODEL})...")
    try:
        proc = subprocess.Popen(["agy", "-p", prompt, "--model", MODEL, "--dangerously-skip-permissions"],
                                cwd=account, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace")
        with agy_log.open("w", encoding="utf-8") as output:
            try:
                combined, _ = proc.communicate(timeout=TIMEOUT_SECONDS)
                timed_out = False
            except subprocess.TimeoutExpired:
                proc.kill()
                combined, _ = proc.communicate()
                timed_out = True
            for line in combined.splitlines():
                output.write(line + "\n")
                output.flush()
                logger.log("INFO", f"{user}: {line}")
            code = 124 if timed_out else proc.returncode
    except OSError as exc:
        logger.log("ERROR", f"Could not run agy: {exc}")
        return 1
    if timed_out:
        logger.log("ERROR", f"{user}: agy timed out after {TIMEOUT_SECONDS}s; revision failed (see {agy_log})")
        return 1
    if code:
        logger.log("ERROR", f"{user}: agy exited with status {code}; revision failed (see {agy_log})")
        return 1
    size = site_index.stat().st_size
    if size < MIN_SIZE:
        logger.log("ERROR", f"{user}: index.html is smaller than {MIN_SIZE} bytes after revision (see {agy_log})")
        return 1
    logger.log("SUCCESS", f"{user}: revision complete -> {site_index} ({size} bytes)")
    return 0


def main() -> int:
    log_dir = REPO / "logs"
    log_dir.mkdir(exist_ok=True)
    session_log = log_dir / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_revisions_{os.getpid()}.log"
    logger = Logger(session_log)
    try:
        date = input("Enter date (YYYY-MM-DD): ").strip()
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
            logger.log("ERROR", "Date must use YYYY-MM-DD format.")
            return 1
        root = Path(os.environ.get("WEBSITES_ROOT", f"/home/frost/websites/{date}"))
        if not root.is_dir():
            logger.log("ERROR", f"Websites directory not found: {root}")
            return 1
        revisions = REPO / "config/REVISIONS.md"
        accounts_file = REPO / "config/accounts.txt"
        if not revisions.is_file():
            logger.log("ERROR", f"Revisions file not found: {revisions}")
            return 1
        if not accounts_file.is_file():
            logger.log("ERROR", f"Accounts file not found: {accounts_file}")
            return 1
        accounts = configured_accounts(accounts_file)
        ok, skipped, failed = [], [], []
        for user, revision in parse_sections(revisions):
            rc = revise(user, revision, root, accounts, logger)
            (ok if rc == 0 else skipped if rc == 2 else failed).append(user)
        logger.log("INFO", "================ Revision summary ================")
        logger.log("SUCCESS", f"Updated: {len(ok)} {' '.join(ok)}")
        logger.log("WARN", f"Skipped: {len(skipped)} {' '.join(skipped)}")
        logger.log("ERROR", f"Failed:  {len(failed)} {' '.join(failed)}")
        return 1 if failed else 0
    except (OSError, EOFError) as exc:
        logger.log("ERROR", str(exc) if str(exc) else "Input ended unexpectedly.")
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
