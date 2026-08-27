"""Enables `python -m inmoai_lt <command>`."""

from __future__ import annotations

import sys

from inmoai_lt.cli import main

if __name__ == "__main__":
    sys.exit(main())
