"""Shared console logging configuration for the profile pipeline."""

import logging
import os
import sys


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
    """Return a consistently formatted pipeline logger without duplicate handlers."""
    logger = logging.getLogger(f"profile_pipeline.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            _ColorFormatter(
                _LOG_FORMAT,
                _DATE_FORMAT,
                use_color=sys.stdout.isatty() and not os.environ.get("NO_COLOR"),
            )
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
