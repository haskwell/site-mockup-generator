#!/usr/bin/env python3
"""Compatibility entrypoint for the site build workflow."""

from src.run import main


if __name__ == "__main__":
    raise SystemExit(main())
