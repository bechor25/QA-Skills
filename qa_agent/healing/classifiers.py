"""Failure-cause classifier — what kind of failure are we looking at?

Different from `flaky.classifier`: this one categorises *deterministic*
failures so the healing engine knows what fix to attempt. The set of
allowed fixes per category lives in `policies.py`.
"""

from __future__ import annotations

import re
from typing import Literal

FailureCategory = Literal[
    "selector",
    "timeout",
    "missing-dependency",
    "auth",
    "assertion",
    "syntax",
    "unknown",
]

_PATTERNS: list[tuple[FailureCategory, re.Pattern[str]]] = [
    ("selector",
     re.compile(r"locator\(.*\) (?:not found|did not (?:resolve|match))|no element matches selector", re.IGNORECASE)),
    ("timeout",
     re.compile(r"timeout|timed out|exceeded.*ms", re.IGNORECASE)),
    ("missing-dependency",
     re.compile(r"ModuleNotFoundError|Cannot find module|ImportError|command not found", re.IGNORECASE)),
    ("auth",
     re.compile(r"401|403|unauthorized|forbidden", re.IGNORECASE)),
    ("syntax",
     re.compile(r"SyntaxError|Unexpected token|invalid syntax", re.IGNORECASE)),
    ("assertion",
     re.compile(r"AssertionError|expect\(.*\)\.to|but got|expected.*to (?:equal|be|contain)", re.IGNORECASE)),
]


def classify_failure(text: str) -> FailureCategory:
    if not text:
        return "unknown"
    for cat, pat in _PATTERNS:
        if pat.search(text):
            return cat
    return "unknown"
