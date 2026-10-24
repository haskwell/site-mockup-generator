#!/usr/bin/env python3
"""Open all generated site index pages for a selected batch date."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    date = input("Enter date (YYYY-MM-DD): ").strip()
    default_root = Path.home() / "websites" / date
    search_dir = Path(os.environ.get("WEBSITES_ROOT", str(default_root))).expanduser()

    if not search_dir.is_dir():
        print(f"Error: Directory not found: {search_dir}")
        return 1

    files = sorted(search_dir.rglob("index.html"))
    if not files:
        print(f"No sites found in: {search_dir}")
        return 0

    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        print("Error: Chromium executable not found on PATH.")
        return 1

    print(f"Opening {len(files)} site(s)")
    subprocess.Popen([chromium, *(str(path) for path in files)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
