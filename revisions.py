#!/usr/bin/env python3
"""Apply non-empty sections from config/REVISIONS.md to generated sites."""

from __future__ import annotations

import re
import os
import datetime as dt
import shutil
import sys
from pathlib import Path
from pipeline_common import Logger, MODEL, MIN_SIZE, TIMEOUT_SECONDS, account_handle, find_agy, run_streaming

REPO = Path(__file__).resolve().parent


def clear_applied_sections(content: str, applied: set[str], accounts: set[str]) -> str:
    out: list[str] = []
    current: str | None = None
    for line in content.splitlines():
        match = re.match(r"^#[ \t]+(\S+)\s*$", line)
        if match:
            current = match.group(1) if match.group(1) in accounts else None
            out.append(line)
        elif current in applied:
            continue
        else:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def parse_sections(path: Path, accounts: set[str]) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_user: str | None = None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        match = re.match(r"^#[ \t]+(\S+)\s*$", line)
        if match:
            if current_user is not None:
                sections.append((current_user, lines))
            candidate = match.group(1)
            current_user = candidate if candidate in accounts else None
            lines = []
        elif current_user is not None:
            lines.append(line)
    if current_user is not None:
        sections.append((current_user, lines))
    return [(user, "\n".join(lines).strip() + "\n") for user, lines in sections if user in accounts]


def configured_accounts(path: Path) -> set[str]:
    users = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip()
        if value:
            try:
                users.add(account_handle(value))
            except ValueError:
                continue
    return users


def revise(user: str, revision: str, root: Path, accounts: set[str], logger: Logger,
           *, emit=None, model: str = MODEL, timeout: int = TIMEOUT_SECONDS) -> int:
    def report(status: str, line: str = ""):
        if emit: emit(user, status, line)
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
    agy_bin = find_agy()
    if not agy_bin:
        message = "agy executable not found on PATH or at ~/.local/bin/agy"
        logger.log("ERROR", f"{user}: {message}")
        report("failed", message)
        return 1
    try:
        (account / "logs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "prompts/GEMINI.md", account / "GEMINI.md")
        shutil.copy2(REPO / "prompts/SKILL.md", account / "SKILL.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to copy generation instructions: {exc}")
        return 1

    agy_log = account / "logs" / f"agy_revision_{dt.datetime.now():%Y-%m-%d_%H%M%S}.log"
    backup = account / "backups" / f"site_before_revision_{dt.datetime.now():%Y%m%d_%H%M%S}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(account / "site", backup)
    prompt = ("Revise the existing website in site/ to address these requested changes. "
              "Preserve its working content and assets unless a requested change requires updating them.\n\n"
              "Revision requests:\n" + revision)
    logger.log("INFO", f"{user}: revising site with agy ({model})...")
    report("building", "Applying revision")
    code, timed_out = run_streaming([agy_bin, "-p", prompt, "--model", model],
                                    account, logger, agy_log, timeout, f"{user}: ")
    if timed_out:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        logger.log("ERROR", f"{user}: agy timed out after {timeout}s; revision failed (see {agy_log})")
        report("failed", "agy timed out")
        return 1
    if code:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        logger.log("ERROR", f"{user}: agy exited with status {code}; revision failed (see {agy_log})")
        report("failed", f"agy exited with status {code}")
        return 1
    size = site_index.stat().st_size
    if size < MIN_SIZE:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        logger.log("ERROR", f"{user}: index.html is smaller than {MIN_SIZE} bytes after revision (see {agy_log})")
        report("failed", f"index.html is smaller than {MIN_SIZE} bytes")
        return 1
    from run import validate_site
    errors = validate_site(account / "site")
    if errors:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        logger.log("ERROR", f"{user}: revised site failed validation: {'; '.join(errors)}")
        report("failed", "; ".join(errors))
        return 1
    logger.log("SUCCESS", f"{user}: revision complete -> {site_index} ({size} bytes)")
    report("done", f"Revision complete: {size} bytes")
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
        root = Path(os.environ.get("WEBSITES_ROOT", str(Path.home() / "websites" / date)))
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
        sections = parse_sections(revisions, accounts)
        for user, revision in sections:
            rc = revise(user, revision, root, accounts, logger)
            (ok if rc == 0 else skipped if rc == 2 else failed).append(user)
        logger.log("INFO", "================ Revision summary ================")
        logger.log("SUCCESS", f"Updated: {len(ok)} {' '.join(ok)}")
        logger.log("WARN", f"Skipped: {len(skipped)} {' '.join(skipped)}")
        logger.log("ERROR", f"Failed:  {len(failed)} {' '.join(failed)}")
        if ok:
            original = revisions.read_text(encoding="utf-8")
            revisions.write_text(clear_applied_sections(original, set(ok), accounts), encoding="utf-8")
        return 1 if failed else 0
    except (OSError, EOFError) as exc:
        logger.log("ERROR", str(exc) if str(exc) else "Input ended unexpectedly.")
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
