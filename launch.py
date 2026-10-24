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
from pathlib import Path


REPO = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765"
STATE_URL = f"{URL}/api/state"


def server_is_running() -> bool:
    try:
        with urllib.request.urlopen(STATE_URL, timeout=1):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> int:
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        print("Error: Chromium executable not found on PATH.", file=sys.stderr)
        return 1

    profile = Path.home() / ".cache" / "studio-profile"
    browser_command = [
        chromium,
        f"--app={URL}",
        f"--user-data-dir={profile}",
        "--window-size=1500,800",
    ]

    # Match launch.sh: if a dashboard is already running, open it and exit.
    if server_is_running():
        return subprocess.run(browser_command, check=False).returncode

    venv_python = REPO / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(venv_python) if venv_python.is_file() else sys.executable
    log_dir = REPO / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = (log_dir / "server.log").open("a", encoding="utf-8")
    server = subprocess.Popen(
        [python, str(REPO / "app.py")],
        cwd=REPO,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        while not server_is_running():
            if server.poll() is not None:
                return 1
            time.sleep(0.3)
        return subprocess.run(browser_command, check=False).returncode
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        log_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
