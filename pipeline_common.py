"""Shared pipeline settings, logging, account parsing, and subprocess helpers."""
from __future__ import annotations

import datetime as dt
import os
import re
import signal
import selectors
import subprocess
import sys
from pathlib import Path

MODEL = "gemini-3.8-flash-medium"
MIN_SIZE = 600
TIMEOUT_SECONDS = 900


class Logger:
    def __init__(self, path: Path):
        self.file = path.open("a", encoding="utf-8")
        self.color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.colors = {"INFO": "\033[36m", "SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m"}

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


def run_streaming(command: list[str], cwd: Path, logger: Logger | None = None,
                  log_path: Path | None = None, timeout: int | None = None,
                  prefix: str = "", cancel_event=None) -> tuple[int, bool]:
    """Stream output as it arrives; kill the whole process group on timeout."""
    try:
        proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace",
                                bufsize=1, start_new_session=True)
    except OSError as exc:
        (logger.log("ERROR", f"Could not run {command[0]}: {exc}") if logger else print(exc, file=sys.stderr))
        return 127, False
    import time
    deadline = None if timeout is None else time.monotonic() + timeout
    output_file = log_path.open("w", encoding="utf-8") if log_path else None
    timed_out = False
    try:
        assert proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        pending = ""
        while True:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return 130, False
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            if remaining == 0:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                break
            ready = selector.select(0.25 if remaining is None else min(0.25, remaining))
            if ready:
                raw = os.read(proc.stdout.fileno(), 8192)
                if not raw:
                    break
                chunk = raw.decode("utf-8", "replace")
                pending += chunk
                chunks = pending.split("\n")
                pending = chunks.pop()
                for line in chunks:
                    line = line.rstrip("\r")
                    if output_file:
                        output_file.write(line + "\n")
                        output_file.flush()
                    if logger:
                        logger.log("INFO", prefix + line)
                    else:
                        print(line, flush=True)
            if proc.poll() is not None and not ready:
                if pending:
                    if output_file:
                        output_file.write(pending + "\n")
                    if logger:
                        logger.log("INFO", prefix + pending)
                    else:
                        print(pending, flush=True)
                    pending = ""
                break
        if timed_out:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return (124 if timed_out else proc.wait()), timed_out
    finally:
        if output_file:
            output_file.close()
        if proc.stdout:
            proc.stdout.close()
