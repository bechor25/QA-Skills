"""Assertion validator.

Static checks against generated test files. Catches:

  - `expect(true).toBe(true)`, `expect(1).toBe(1)` (vacuous truth)
  - `assert True`, `assert 1 == 1`
  - empty `it` / `test` bodies
  - `expect(...)` with no `.to*` chain
  - completely missing assertion keywords

Returns a list of CritiqueFinding ready to fold into a CritiqueResult.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..state import schemas

# Patterns are intentionally broad — false positives are downgraded to warnings.
_PATTERNS_ERROR: list[tuple[str, re.Pattern[str], str]] = [
    ("vacuous-expect-true",
     re.compile(r"expect\s*\(\s*true\s*\)\s*\.\s*toBe(?:Truthy)?\s*\(\s*true\s*\)", re.IGNORECASE),
     "vacuous assertion: expect(true).toBe(true)"),
    ("vacuous-expect-equal-self",
     re.compile(r"expect\s*\(\s*(\d+)\s*\)\s*\.\s*toBe\s*\(\s*\1\s*\)"),
     "vacuous assertion: expect(N).toBe(N) with N equal to itself"),
    ("python-assert-true",
     re.compile(r"^\s*assert\s+True\s*$", re.MULTILINE),
     "vacuous assertion: bare `assert True`"),
    ("python-assert-self-equal",
     re.compile(r"^\s*assert\s+(\w+)\s*==\s*\1\s*$", re.MULTILINE),
     "vacuous assertion: `assert x == x`"),
]

_PATTERNS_WARN: list[tuple[str, re.Pattern[str], str]] = [
    ("empty-it-body",
     re.compile(r"(?:it|test)\s*\([^)]*,\s*(?:async\s*)?\(\s*\)\s*=>\s*\{\s*\}", re.IGNORECASE),
     "test body is empty"),
    ("expect-without-matcher",
     re.compile(r"^\s*expect\s*\([^)]*\)\s*;\s*$", re.MULTILINE),
     "expect() call with no matcher"),
]


def validate_test_file(path: Path) -> list[schemas.CritiqueFinding]:
    """Run all assertion checks against the test file at `path`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return [schemas.CritiqueFinding(rule="read-failed", severity="error", message=str(e))]

    findings: list[schemas.CritiqueFinding] = []
    for rule, pat, msg in _PATTERNS_ERROR:
        for m in pat.finditer(text):
            findings.append(_finding(rule, "error", msg, text, m.start()))
    for rule, pat, msg in _PATTERNS_WARN:
        for m in pat.finditer(text):
            findings.append(_finding(rule, "warning", msg, text, m.start()))

    # Heuristic: any test file that lacks an assertion keyword at all
    # is suspicious — flag as a single warning rather than a hard error.
    if not _has_any_assertion(text):
        findings.append(
            schemas.CritiqueFinding(
                rule="no-assertion",
                severity="warning",
                message="file contains no `expect(`/`assert ` keyword",
            )
        )
    return findings


def _has_any_assertion(text: str) -> bool:
    return ("expect(" in text) or re.search(r"^\s*assert\s+", text, re.MULTILINE) is not None


def _finding(rule: str, severity: str, msg: str, text: str, idx: int) -> schemas.CritiqueFinding:
    line = text.count("\n", 0, idx) + 1
    return schemas.CritiqueFinding(rule=rule, severity=severity, message=msg, line=line)  # type: ignore[arg-type]
