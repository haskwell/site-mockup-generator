#!/usr/bin/env python3
"""Unified entry point for the desktop executable and subprocess dispatcher."""

from __future__ import annotations

import multiprocessing
import os
import sys

# Windows windowed (console=False) safeguard against NoneType stream crashes
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def dispatch_subcommand() -> bool:
    """Check if this process invocation is an internal subtask or server."""
    if len(sys.argv) < 2:
        return False

    first_arg = sys.argv[1].replace("\\", "/").lower()

    if first_arg.endswith("app.py") or first_arg == "--server":
        os.environ.setdefault("PYTHONUTF8", "1")
        import uvicorn
        from src.app import app

        sys.argv.pop(1)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=int(os.environ.get("PORT", 8765)),
            reload=False,
        )
        return True

    if first_arg.endswith("scraper.py") or first_arg == "scraper":
        from src.scraper import main as scraper_main

        sys.argv.pop(1)
        scraper_main()
        return True

    if first_arg.endswith("profile_summary.py") or first_arg == "profile_summary":
        from src.profile_summary import main as summary_main

        sys.argv.pop(1)
        summary_main()
        return True

    if first_arg.endswith("update_sheet.py") or first_arg == "update_sheet":
        from src.update_sheet import main as sheet_main

        sys.argv.pop(1)
        raise SystemExit(sheet_main())

    if first_arg.endswith("design.py") or first_arg == "design":
        from src.design import main as design_main

        sys.argv.pop(1)
        design_main()
        return True

    return False


def main() -> int:
    if dispatch_subcommand():
        return 0

    import launch

    return launch.main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
