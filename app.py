#!/usr/bin/env python3
"""Compatibility entrypoint for the local dashboard."""

import os

import uvicorn

from src.app import app


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    reload_opt = os.environ.get("STUDIO_RELOAD", "").strip().lower() in {"1", "true", "yes"}
    uvicorn.run("src.app:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8765)), reload=reload_opt)
