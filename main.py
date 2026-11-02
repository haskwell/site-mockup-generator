#!/usr/bin/env python3
"""Unified entry point for Studio.

Usage:
    python main.py             Launch the desktop GUI application
    python main.py --server    Start the background FastAPI server directly
    python main.py <subcmd>    Execute internal pipeline subprocess
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import traceback
from pathlib import Path


def show_fatal_error(title: str, msg: str) -> None:
    """Display native message box on Windows so startup errors are never swallowed."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
        except Exception:
            pass


def setup_crash_logging() -> None:
    """Redirect stdout/stderr to persistent log files and set a global crash handler."""
    log_dir = Path(os.environ.get("TEMP", "/tmp")) / "Studio_Logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "studio_startup.log"
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log_file
        if sys.stderr is None:
            sys.stderr = log_file
    except Exception:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")

    def global_excepthook(exc_type, exc_val, exc_tb):
        err = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        try:
            sys.stderr.write(f"\n[FATAL CRASH] {err}\n")
            sys.stderr.flush()
        except Exception:
            pass
        show_fatal_error(
            "Studio Startup Error",
            f"Studio encountered an unhandled exception during startup:\n\n{err}\n\nLog saved to:\n%TEMP%\\Studio_Logs\\studio_startup.log"
        )

    sys.excepthook = global_excepthook


setup_crash_logging()


def dispatch_subcommand() -> bool:
    """Check if this process invocation is an internal subtask or server."""
    if len(sys.argv) < 2:
        return False

    first_arg = sys.argv[1].replace("\\", "/").lower()

    if first_arg in {"--help", "-h"}:
        print(__doc__.strip())
        return True

    if first_arg in {"--server", "server"} or first_arg.endswith("app.py"):
        os.environ.setdefault("PYTHONUTF8", "1")
        import uvicorn
        from src.server.app import app

        sys.argv.pop(1)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=int(os.environ.get("PORT", 8765)),
            reload=False,
        )
        return True

    if first_arg in {"scraper", "src.pipeline.scraper"} or first_arg.endswith("scraper.py"):
        from src.pipeline.scraper import main as scraper_main

        sys.argv.pop(1)
        scraper_main()
        return True

    if first_arg in {"profile_summary", "summary", "src.pipeline.summary"} or first_arg.endswith(
        ("profile_summary.py", "summary.py")
    ):
        from src.pipeline.summary import main as summary_main

        sys.argv.pop(1)
        summary_main()
        return True

    if first_arg in {"update_sheet", "sheets", "src.pipeline.sheets"} or first_arg.endswith(
        ("update_sheet.py", "sheets.py")
    ):
        from src.pipeline.sheets import main as sheet_main

        sys.argv.pop(1)
        raise SystemExit(sheet_main())

    if first_arg in {"design", "src.pipeline.design"} or first_arg.endswith("design.py"):
        from src.pipeline.design import main as design_main

        sys.argv.pop(1)
        design_main()
        return True

    return False


def main() -> int:
    try:
        from src.storage.credentials import hydrate_environment
        hydrate_environment()
    except Exception:
        pass

    if dispatch_subcommand():
        return 0

    from src.core.launcher import launch_desktop

    return launch_desktop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
