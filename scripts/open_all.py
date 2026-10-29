#!/usr/bin/env python3
"""Open all generated site index pages for a selected batch date."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    date = input("Enter date (YYYY-MM-DD): ").strip()
    base_root = Path(os.environ.get("WEBSITES_ROOT", Path.home() / "websites")).expanduser().resolve()
    search_dir = base_root if base_root.name == date else base_root / date

    if not search_dir.is_dir():
        print(f"Error: Directory not found: {search_dir}")
        return 1

    import webbrowser

    files = sorted(search_dir.rglob("index.html"))
    if not files:
        print(f"No sites found in: {search_dir}")
        return 0

    browser = None
    for name in ["chromium", "chromium-browser", "chrome", "google-chrome", "msedge"]:
        path = shutil.which(name)
        if path:
            browser = path
            break

    if not browser and os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for cand in candidates:
            if cand.is_file():
                browser = str(cand)
                break

    print(f"Opening {len(files)} site(s)")
    if browser:
        # Open in chunks of 20 to avoid OS command line length limits on Windows
        chunk_size = 20
        for i in range(0, len(files), chunk_size):
            chunk = files[i:i + chunk_size]
            subprocess.Popen([browser, *(str(path) for path in chunk)])
    else:
        for path in files:
            webbrowser.open(path.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
