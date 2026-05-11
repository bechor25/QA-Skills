"""Logging setup for qa_agent.

A thin wrapper over stdlib logging — Rich-formatted when available.
"""

from __future__ import annotations

import logging
import os
import sys

_DEFAULT_LEVEL = "INFO"
_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Idempotent."""
    _ensure_configured()
    return logging.getLogger(name)


def _ensure_configured() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.environ.get("QA_AGENT_LOG_LEVEL", _DEFAULT_LEVEL).upper()
    level = getattr(logging, level_name, logging.INFO)

    handler: logging.Handler
    try:
        from rich.logging import RichHandler

        handler = RichHandler(
            rich_tracebacks=True,
            markup=False,
            show_path=False,
            show_time=True,
        )
        fmt = "%(message)s"
    except ImportError:  # pragma: no cover — rich is a declared dep
        handler = logging.StreamHandler(stream=sys.stderr)
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    _CONFIGURED = True
