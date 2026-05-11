"""Shared stub-content markers — single source of truth.

These literal substrings identify a placeholder/auto-generated stub test file.
Any file whose body contains *any* of these markers is NOT a real test and
MUST NOT count toward coverage; it also escalates final_gate status to
`partial` and is listed in the HTML report banner.

Markers are stub-language only (no project names, no framework imports, no
domain-specific regex). Adding a project to QA-Skills must never require
editing this list.
"""

from __future__ import annotations

STUB_MARKERS: tuple[str, ...] = (
    # canonical signature emitted by historical fallback path
    "Auto-generated stub",
    "Auto-generated stub.",
    # placeholder bodies
    "placeholder — add",
    "// Placeholder — enhance",
    "TODO: import and test",
    "TODO: Use axe-playwright",
    "TODO: Navigate to the component",
    # tautological assertion bodies (vitest/jest/pytest)
    "expect(true).toBe(true)",
    "expect(true).toBeTruthy()",
    "assert True  # placeholder",
)


def is_stub(content: str) -> bool:
    """Return True if `content` contains any stub marker."""
    return any(m in content for m in STUB_MARKERS)


__all__ = ["STUB_MARKERS", "is_stub"]
