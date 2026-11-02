"""Desktop window launcher for Studio."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from src.core.common import IS_FROZEN, REPO_ROOT, get_venv_python, kill_process_tree

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


def launch_desktop() -> int:
    browser_bin = find_browser()
    if os.name == "nt":
        cache_base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")))
    else:
        cache_base = Path.home() / ".cache"
    profile = cache_base / "studio-profile"

    if server_is_running():
        return open_browser(profile, browser_bin)

    server: subprocess.Popen | None = None
    server_thread: threading.Thread | None = None
    server_errors: list[str] = []
    srv_instance: Any = None
    log_file = None

    if IS_FROZEN:
        try:
            import uvicorn
            from src.server.app import app

            def _run_server() -> None:
                nonlocal srv_instance
                try:
                    config = uvicorn.Config(
                        app,
                        host="127.0.0.1",
                        port=PORT,
                        log_level="info",
                        access_log=False,
                    )
                    srv_instance = uvicorn.Server(config)
                    srv_instance.run()
                except Exception:
                    import traceback
                    tb = traceback.format_exc()
                    server_errors.append(tb)
                    print(f"\n[SERVER THREAD CRASH] {tb}\n", file=sys.stderr)

            server_thread = threading.Thread(target=_run_server, daemon=True)
            server_thread.start()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            server_errors.append(tb)
            print(f"\n[SERVER IMPORT CRASH] {tb}\n", file=sys.stderr)
    else:
        python = get_venv_python(REPO)
        log_dir = REPO / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = (log_dir / "server.log").open("a", encoding="utf-8")
        server_kwargs: dict = {
            "cwd": REPO,
            "stdin": subprocess.DEVNULL,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            server_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            server_kwargs["start_new_session"] = True
        
        main_script = REPO / "main.py"
        server_cmd = [python, str(main_script), "--server"] if main_script.is_file() else [python, "-m", "src.server.app"]
        server = subprocess.Popen(server_cmd, **server_kwargs)

    try:
        startup_deadline = time.monotonic() + 30.0
        while not server_is_running():
            if server is not None and server.poll() is not None:
                return 1
            if server_thread is not None and not server_thread.is_alive():
                err_detail = server_errors[0] if server_errors else "Thread exited unexpectedly without details."
                print(f"Error: Background server thread terminated unexpectedly:\n{err_detail}", file=sys.stderr)
                if sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.user32.MessageBoxW(
                            0,
                            f"Studio background server failed to start:\n\n{err_detail}",
                            "Studio Server Crash",
                            0x10,
                        )
                    except Exception:
                        pass
                return 1
            if time.monotonic() > startup_deadline:
                print("Error: Server failed to start and respond to /api/ping within 30s.", file=sys.stderr)
                if sys.platform == "win32":
                    try:
                        import ctypes
                        ctypes.windll.user32.MessageBoxW(
                            0,
                            f"Studio server did not respond at http://127.0.0.1:{PORT}/ within 30 seconds.\n"
                            f"Port {PORT} may be occupied or blocked by antivirus/firewall.",
                            "Studio Startup Timeout",
                            0x10,
                        )
                    except Exception:
                        pass
                return 1
            time.sleep(0.2)
        open_browser(profile, browser_bin)

        # When open_browser returns, the user has closed the app window.
        # Shut down background server cleanly and terminate process.
        if server is not None and server.poll() is None:
            kill_process_tree(server)
            try:
                server.wait(timeout=3)
            except Exception:
                pass
        elif server_thread is not None:
            if srv_instance is not None:
                srv_instance.should_exit = True
            server_thread.join(timeout=2)
            os._exit(0)
        return 0
    finally:
        if server is not None and server.poll() is None:
            kill_process_tree(server)
            try:
                server.wait(timeout=3)
            except Exception:
                pass
        if log_file is not None:
            log_file.close()
        # Ensure frozen process never lingers in background
        if IS_FROZEN:
            os._exit(0)


def main() -> int:
    return launch_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
