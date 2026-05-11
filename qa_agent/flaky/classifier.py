"""Heuristic classifier for flaky test failures.

Inspects stderr/stdout tails from re-run attempts and bucket-classifies
the instability. The buckets are aligned with `FlakyEntry.classification`.
"""

from __future__ import annotations

import re
from typing import Literal

Classification = Literal["timing", "network", "env", "race", "order"]

_RULES: list[tuple[Classification, re.Pattern[str]]] = [
    ("timing", re.compile(r"timeout|exceeded|deadline|playwright.*timeout|TimeoutError", re.IGNORECASE)),
    ("network", re.compile(r"connection refused|ECONNRESET|ETIMEDOUT|ENOTFOUND|getaddrinfo", re.IGNORECASE)),
    ("env",    re.compile(r"missing env|env.*not set|undefined.*environment|permission denied", re.IGNORECASE)),
    ("race",   re.compile(r"race condition|atomic|stale|concurrently|state inconsistent", re.IGNORECASE)),
    ("order",  re.compile(r"depends on previous|fixture not found|teardown leaked|isolated", re.IGNORECASE)),
]


def classify(text: str) -> Classification:
    """Return the most likely classification for the given log text."""
    if not text:
        return "timing"
    for cls, pat in _RULES:
        if pat.search(text):
            return cls
    return "timing"
