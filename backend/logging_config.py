"""Centralized logging configuration for the Finance Clawbot backend.

Call ``setup_logging()`` once at app startup (before any request is served).
All modules should use ``logging.getLogger(__name__)`` to get their logger.
"""
from __future__ import annotations

import logging
import sys

from config import Config


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_level(raw: str) -> int:
    level = getattr(logging, str(raw).upper(), None)
    return level if isinstance(level, int) else logging.INFO


def setup_logging(level: int | None = None) -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    effective_level = level if level is not None else _parse_level(Config.LOG_LEVEL)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(effective_level)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.INFO)
