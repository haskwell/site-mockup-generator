#!/usr/bin/env python3
"""Start the local dashboard and open it in Chromium."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from src.pipeline_common import REPO_ROOT, get_venv_python, kill_process_tree

REPO = REPO_ROOT
try:
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
except Exception:
    pass

PORT = int(os.environ.get("PORT", 8765))
URL = f"http://127.0.0.1:{PORT}"
STATE_URL = f"{URL}/api/state"
PING_URL = f"{URL}/api/ping"


def _current_url() -> str:
    port_env = os.environ.get("PORT")
    if port_env:
        return f"http://127.0.0.1:{int(port_env)}"
    return URL


def _current_state_url() -> str:
    port_env = os.environ.get("PORT")
    if port_env:
        return f"http://127.0.0.1:{int(port_env)}/api/state"
    return STATE_URL


def _current_ping_url() -> str:
    port_env = os.environ.get("PORT")
    if port_env:
        return f"http://127.0.0.1:{int(port_env)}/api/ping"
    return PING_URL


def server_is_running() -> bool:
    try:
        with urllib.request.urlopen(_current_ping_url(), timeout=1):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


def find_browser() -> str | None:
    for name in ["chromium", "chromium-browser", "chrome", "google-chrome", "msedge"]:
        path = shutil.which(name)
        if path:
            return path
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Google/Chrome/Application/chrome.exe")
        for cand in candidates:
            if cand.is_file():
                return str(cand)
    return None


def open_browser(profile: Path, browser_bin: str | None) -> int:
    target_url = _current_url()
    if browser_bin:
        cmd = [
            browser_bin,
            f"--app={target_url}",
            f"--user-data-dir={profile}",
            "--window-size=1500,800",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=msEdgeStartupBoost",
        ]
        return subprocess.run(cmd, check=False).returncode
    webbrowser.open(target_url)
    return 0


def main() -> int:
    browser_bin = find_browser()
    if os.name == "nt":
        cache_base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")))
    else:
        cache_base = Path.home() / ".cache"
    profile = cache_base / "studio-profile"

    # Match launch.sh: if a dashboard is already running, open it and exit.
    if server_is_running():
        return open_browser(profile, browser_bin)

    python = get_venv_python(REPO)
    log_dir = REPO / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = (log_dir / "server.log").open("a", encoding="utf-8")
    server_kwargs: dict = {
        "cwd": REPO,
        "stdin": subprocess.DEVNULL,  # pythonw has no stdin to inherit
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        # CREATE_NO_WINDOW stops the console from flashing up when
        # launched via pythonw.exe
        server_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        server_kwargs["start_new_session"] = True
    server = subprocess.Popen([python, str(REPO / "app.py")], **server_kwargs)

    try:
        startup_deadline = time.monotonic() + 30.0
        while not server_is_running():
            if server.poll() is not None:
                return 1
            if time.monotonic() > startup_deadline:
                print("Error: Server failed to start and respond to /api/ping within 30s.", file=sys.stderr)
                return 1
            time.sleep(0.3)
        open_browser(profile, browser_bin)
        # On Windows Edge, open_browser may return immediately because Edge delegates
        # to its background process. Keep the launcher alive until the server shuts down.
        if server.poll() is None:
            try:
                server.wait()
            except KeyboardInterrupt:
                pass
        return 0
    finally:
        if server.poll() is None:
            kill_process_tree(server)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        log_file.close()


if __name__ == "__main__":
    raise SystemExit(main())