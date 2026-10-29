"""Shared timestamped console logging for the profile pipeline."""

import logging
import os
import sys
import threading

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"
_CONFIGURED = False
_CONFIG_LOCK = threading.Lock()


class _ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: str, *, use_color: bool) -> None:
        super().__init__(fmt, datefmt=datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_color:
            return super().format(record)

        record = logging.makeLogRecord(record.__dict__.copy())
        color = _LEVEL_COLORS.get(record.levelno)
        if color:
            record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Return a consistently formatted console logger."""
    global _CONFIGURED
    logger = logging.getLogger(f"profile_pipeline.{name}")
    if not _CONFIGURED:
        with _CONFIG_LOCK:
            if not _CONFIGURED:
                console = logging.StreamHandler(sys.stdout)
                console.setFormatter(
                    _ColorFormatter(_LOG_FORMAT, _DATE_FORMAT,
                                    use_color=sys.stdout.isatty() and not os.environ.get("NO_COLOR"))
                )
                root = logging.getLogger("profile_pipeline")
                root.setLevel(logging.INFO)
                root.addHandler(console)
                _CONFIGURED = True
    logger.setLevel(logging.INFO)
    logger.propagate = True
    return logger
