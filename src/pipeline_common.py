"""Shared pipeline settings, logging, account parsing, and subprocess helpers."""

from __future__ import annotations

import datetime as dt
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

MODEL = "gemini-3.8-flash-medium"
MIN_SIZE = 600
TIMEOUT_SECONDS = 900


def get_venv_python(repo_dir: Path) -> str:
    """Return the virtual environment's python executable or fallback to sys.executable."""
    venv_python = (
        repo_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and all of its child processes cross-platform."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,  # no console flash
                check=False,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass


def find_agy() -> str | None:
    """Find agy on PATH or in standard per-user executable directories."""
    executable = shutil.which("agy")
    if executable:
        return executable
    if os.name == "nt":
        candidates = [
            Path.home() / ".local" / "bin" / "agy.exe",
            Path.home() / ".local" / "bin" / "agy.cmd",
            Path.home() / ".local" / "bin" / "agy",
        ]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.extend(
                [
                    Path(local_app_data) / "Programs" / "agy" / "agy.exe",
                    Path(local_app_data) / "Programs" / "agy" / "bin" / "agy.exe",
                ]
            )
        for cand in candidates:
            if cand.is_file():
                return str(cand)
    else:
        user_executable = Path.home() / ".local" / "bin" / "agy"
        if user_executable.is_file() and os.access(user_executable, os.X_OK):
            return str(user_executable)
    return None


class Logger:
    def __init__(self, path: Path):
        self.file = path.open("a", encoding="utf-8")
        self.color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.colors = {
            "INFO": "\033[36m",
            "SUCCESS": "\033[32m",
            "WARN": "\033[33m",
            "ERROR": "\033[31m",
        }

    def log(self, level: str, message: str) -> None:
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = self.colors.get(level, self.colors["INFO"]) if self.color else ""
        reset = "\033[0m" if self.color else ""
        line = f"{stamp} {color}{level:<8}{reset} {message}"
        print(line, flush=True)
        self.file.write(re.sub(r"\033\[[0-9;]*m", "", line) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def account_handle(value: str) -> str:
    value = value.strip()
    if value.startswith(("https://", "http://")):
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.hostname not in {"instagram.com", "www.instagram.com"}:
            raise ValueError(f"unsupported account URL: {value}")
        parts = [p for p in parsed.path.split("/") if p]
        if not parts or parts[0] in {"p", "reel", "stories", "accounts"}:
            raise ValueError(f"URL is not an Instagram profile: {value}")
        value = parts[0]
    value = value.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9._]+", value) or value in {".", ".."}:
        raise ValueError(f"invalid Instagram handle: {value!r}")
    return value


def run_streaming(
    command: list[str],
    cwd: Path,
    logger: Logger | None = None,
    log_path: Path | None = None,
    timeout: int | None = None,
    prefix: str = "",
    cancel_event=None,
) -> tuple[int, bool]:
    """Stream output as it arrives; kill the whole process group on timeout or cancellation."""
    popen_kwargs: dict = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "errors": "replace",
        "bufsize": 1,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(command, **popen_kwargs)
    except OSError as exc:
        (
            logger.log("ERROR", f"Could not run {command[0]}: {exc}")
            if logger
            else print(exc, file=sys.stderr)
        )
        return 127, False

    deadline = None if timeout is None else time.monotonic() + timeout
    output_file = log_path.open("w", encoding="utf-8") if log_path else None
    timed_out = False

    output_queue: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        try:
            assert proc.stdout is not None
            for raw_line in iter(proc.stdout.readline, ""):
                output_queue.put(raw_line)
        except Exception:
            pass
        finally:
            output_queue.put(None)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                kill_process_tree(proc)
                return 130, False

            remaining = (
                None if deadline is None else max(0, deadline - time.monotonic())
            )
            if remaining == 0:
                timed_out = True
                kill_process_tree(proc)
                break

            poll_timeout = 0.25 if remaining is None else min(0.25, remaining)
            try:
                line = output_queue.get(timeout=poll_timeout)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue

            if line is None:
                break

            clean_line = line.rstrip("\r\n")
            if output_file:
                output_file.write(clean_line + "\n")
                output_file.flush()
            if logger:
                logger.log("INFO", prefix + clean_line)
            else:
                print(clean_line, flush=True)

        if timed_out:
            kill_process_tree(proc)

        return (124 if timed_out else proc.wait()), timed_out
    finally:
        if output_file:
            output_file.close()
        if proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass
