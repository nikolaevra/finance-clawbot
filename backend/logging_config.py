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
    effective_level = level if level is not None else _parse_level(Config.LOG_LEVEL)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)
    root.setLevel(effective_level)

    # Railway marks stderr output as error logs. Redirect logger stream handlers
    # to stdout so INFO/WARNING lines are not misclassified.
    for logger_name in (
        "",
        "gunicorn.error",
        "gunicorn.access",
        "celery",
        "celery.beat",
        "celery.worker",
        "celery.redirected",
    ):
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and getattr(handler, "stream", None) is sys.stderr
            ):
                handler.stream = sys.stdout

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.INFO)
