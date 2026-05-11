"""classify_diff tests — pure functional, no git required."""

from __future__ import annotations

import pytest

from qa_skills.git_diff import classify_diff


def _diff(*lines: str) -> str:
    """Build a minimal git-diff-like blob from added (+) / removed (-) lines."""
    body = ["diff --git a/x b/x", "index 0..1 100644", "--- a/x", "+++ b/x", "@@ -1,1 +1,1 @@"]
    body.extend(lines)
    return "\n".join(body)


def test_unchanged_when_diff_empty():
    assert classify_diff("", "python") == "unchanged"


def test_unknown_when_diff_none():
    assert classify_diff(None, "python") == "unknown"


def test_signature_change_python_def():
    diff = _diff("- def login(email):", "+ def login(email, password):")
    assert classify_diff(diff, "python") == "signature_changed"


def test_signature_change_python_class():
    diff = _diff("+ class UserService:")
    assert classify_diff(diff, "python") == "signature_changed"


def test_signature_change_route_decorator():
    diff = _diff("+ @app.route('/api/login')")
    assert classify_diff(diff, "python") == "signature_changed"


def test_signature_change_typescript_function():
    diff = _diff("+ function login(email: string, password: string) {")
    assert classify_diff(diff, "typescript") == "signature_changed"


def test_trivial_python_comment_only():
    diff = _diff("- # old comment", "+ # new comment")
    assert classify_diff(diff, "python") == "trivial"


def test_trivial_typescript_comment_only():
    diff = _diff("- // old", "+ // new")
    assert classify_diff(diff, "typescript") == "trivial"


def test_trivial_string_literal_only():
    diff = _diff('- "old message"', '+ "new message"')
    assert classify_diff(diff, "python") == "trivial"


def test_body_change_default():
    diff = _diff("- result = compute()", "+ result = compute_v2()")
    assert classify_diff(diff, "python") == "body_changed"


def test_signature_takes_precedence_over_body():
    diff = _diff("+ def foo(x):", "+ result = compute()")
    assert classify_diff(diff, "python") == "signature_changed"
