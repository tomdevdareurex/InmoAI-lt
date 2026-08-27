"""Logging setup: file + console, no bare `print()` as logging."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logging(log_dir: Path, reference_date_label: str) -> logging.Logger:
    """Configure the `inmoai_lt` logger to write to both console and a dated log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"cleaning_{reference_date_label}.log"

    logger = logging.getLogger("inmoai_lt")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Some Windows consoles use a non-UTF-8 code page (e.g. cp1252) and cannot render
    # Lithuanian diacritics; fall back to replacement characters on the console only.
    # The log file above is always written as UTF-8 and never loses information.
    console_stream = sys.stdout
    if hasattr(console_stream, "reconfigure"):
        try:
            console_stream.reconfigure(errors="backslashreplace")
        except (ValueError, AttributeError):
            pass
    console_handler = logging.StreamHandler(console_stream)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
