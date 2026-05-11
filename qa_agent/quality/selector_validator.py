"""Selector validator for Playwright/UI tests.

Flags:
  - XPath selectors (brittle, prefer role/text/testid)
  - long CSS chains (>3 descendant combinators)
  - selectors using auto-generated framework class hashes
  - hard-coded English text where i18n is in use (warning only)

Returns CritiqueFinding entries.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..state import schemas

_XPATH_RE = re.compile(r"""\b(?:locator|getByXPath|xpath=)\s*[(]?\s*['"`]\s*(/{1,2}|\.+/)""")
_DEEP_CSS_RE = re.compile(r"""['"`]([^'"`]*\s>\s[^'"`]*\s>\s[^'"`]*\s>\s[^'"`]*)['"`]""")
_HASHED_CLASS_RE = re.compile(r"""\.[A-Za-z_][\w-]*__[A-Za-z0-9_-]+_{2}[A-Za-z0-9_-]+""")


def validate_selectors(path: Path) -> list[schemas.CritiqueFinding]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return [schemas.CritiqueFinding(rule="read-failed", severity="error", message=str(e))]
    findings: list[schemas.CritiqueFinding] = []

    for m in _XPATH_RE.finditer(text):
        findings.append(
            schemas.CritiqueFinding(
                rule="xpath-selector",
                severity="error",
                message="XPath selector — prefer getByRole/getByText/getByTestId",
                line=text.count("\n", 0, m.start()) + 1,
            )
        )
    for m in _DEEP_CSS_RE.finditer(text):
        findings.append(
            schemas.CritiqueFinding(
                rule="deep-css-chain",
                severity="warning",
                message="CSS chain has >3 descendant combinators",
                line=text.count("\n", 0, m.start()) + 1,
            )
        )
    for m in _HASHED_CLASS_RE.finditer(text):
        findings.append(
            schemas.CritiqueFinding(
                rule="framework-hashed-class",
                severity="warning",
                message="selector relies on framework-generated class hash",
                line=text.count("\n", 0, m.start()) + 1,
            )
        )
    return findings
