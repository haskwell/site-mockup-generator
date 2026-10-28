#!/usr/bin/env python3
"""Apply non-empty sections from config/REVISIONS.md to generated sites."""

from __future__ import annotations

import re
import os
import datetime as dt
import shutil
import sys
import time
from pathlib import Path
from src.pipeline_common import Logger, MODEL, MIN_SIZE, TIMEOUT_SECONDS, account_handle, find_agy, run_streaming, REPO_ROOT, get_asset_path
from src.r2_storage import download_site, get_lead_text, get_r2_mtime, is_r2_configured, upload_file, upload_site

REPO = REPO_ROOT


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
           *, emit=None, model: str = MODEL, timeout: int = TIMEOUT_SECONDS,
           cancel_event=None) -> int:
    def report(status: str, line: str = ""):
        if emit: emit(user, status, line)
    if not revision.strip():
        return 2
    if user not in accounts:
        logger.log("ERROR", f"Unknown account heading '#{user}'; skipping")
        return 1
    account = root / user
    site_index = account / "site/index.html"
    if is_r2_configured():
        r2_mtime = get_r2_mtime(f"{root.name}/{user}/site/index.html")
        if not site_index.is_file() or (r2_mtime is not None and r2_mtime > site_index.stat().st_mtime):
            logger.log("INFO", f"{user}: pulling latest site files from Cloudflare R2 for revision...")
            download_site(root.name, user, account / "site")
            if r2_mtime is not None and site_index.is_file():
                try:
                    os.utime(site_index, (r2_mtime, r2_mtime))
                except Exception:
                    pass
    if not site_index.is_file():
        logger.log("ERROR", f"{user}: existing site not found at {site_index}")
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
                logger.log("INFO", f"{user}: fetched latest DESIGN.md from Cloudflare R2")
    if not design_file.is_file():
        try:
            design_file.write_text(f"# Design Direction for {user}\nClean, modern, responsive website.\n", encoding="utf-8")
            logger.log("WARN", f"{user}: DESIGN.md missing; created fallback design direction")
        except Exception:
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
        shutil.copy2(get_asset_path("prompts/GEMINI.md"), account / "GEMINI.md")
        shutil.copy2(get_asset_path("prompts/SKILL.md"), account / "SKILL.md")
    except OSError as exc:
        logger.log("ERROR", f"{user}: failed to copy generation instructions: {exc}")
        return 1

    agy_log = account / "logs" / f"agy_revision_{dt.datetime.now():%Y-%m-%d_%H%M%S}_{time.monotonic_ns() % 1000000}.log"
    backup = account / "backups" / f"site_before_revision_{dt.datetime.now():%Y%m%d_%H%M%S}_{time.monotonic_ns() % 1000000}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(account / "site", backup)
    prompt = ("Revise the existing website in site/ to address these requested changes. "
              "Preserve its working content and assets unless a requested change requires updating them.\n\n"
              "Revision requests:\n" + revision)
    logger.log("INFO", f"{user}: revising site with agy ({model})...")
    report("building", "Applying revision")
    # NOTE: --dangerously-skip-permissions is used for automated revisions; revision requests and scraped data are untrusted user input.
    code, timed_out = run_streaming([agy_bin, "-p", prompt, "--model", model,
                                     "--dangerously-skip-permissions"],
                                    account, logger, agy_log, timeout, f"{user}: ",
                                    cancel_event=cancel_event)
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
    size = site_index.stat().st_size if site_index.is_file() else 0
    if not site_index.is_file() or size < MIN_SIZE:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        logger.log("ERROR", f"{user}: index.html is missing or smaller than {MIN_SIZE} bytes after revision (see {agy_log})")
        report("failed", f"index.html is missing or smaller than {MIN_SIZE} bytes")
        return 1
    from src.run import validate_site
    errors = validate_site(account / "site")
    if errors:
        shutil.rmtree(account / "site", ignore_errors=True)
        shutil.copytree(backup, account / "site")
        logger.log("ERROR", f"{user}: revised site failed validation: {'; '.join(errors)}")
        report("failed", "; ".join(errors))
        return 1
    logger.log("SUCCESS", f"{user}: revision complete -> {site_index} ({size} bytes)")
    if is_r2_configured():
        logger.log("INFO", f"{user}: uploading revised site to Cloudflare R2...")
        upload_site(account / "site", root.name, user)
        if design_file.is_file():
            upload_file(design_file, f"{root.name}/{user}/DESIGN.md", "text/markdown")
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
        base_root = Path(os.environ.get("WEBSITES_ROOT", Path.home() / "websites")).expanduser().resolve()
        root = base_root if (base_root.name == date and base_root.is_dir() and not (base_root / date).is_dir()) else base_root / date
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
