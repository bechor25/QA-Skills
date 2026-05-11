"""validators tests — path regex, AgentResult shape, expected_files."""

from __future__ import annotations

from qa_skills.validators import (
    validate_path,
    validate_test_output,
    validate_expected_files,
)


def test_path_regex_python_unit():
    ok, _ = validate_path("tests/unit/auth/test_auth.py")
    assert ok


def test_path_regex_typescript_api():
    ok, _ = validate_path("tests/api/auth/login.api.test.ts")
    assert ok


def test_path_regex_rejects_flat():
    ok, err = validate_path("tests/test_unit.py")
    assert not ok and "path_regex_violation" in err


def test_path_regex_rejects_subpackage_root():
    ok, err = validate_path("sample_app/tests/unit/auth/test_auth.py")
    assert not ok


def test_path_regex_rejects_unknown_category():
    ok, _ = validate_path("tests/perf/auth/test_auth.py")
    assert not ok


def test_validate_test_output_minimal_ok():
    errors = validate_test_output({
        "agent": "qa-api-test",
        "status": "passed",
        "outputs": [{"path": "tests/api/auth/test_login.py"}],
    })
    assert errors == []


def test_validate_test_output_missing_agent():
    errors = validate_test_output({"status": "passed", "outputs": []})
    assert "missing_field:agent" in errors


def test_validate_test_output_skipped_with_reason():
    errors = validate_test_output({
        "agent": "qa-ui-test",
        "status": "skipped:no_server",
        "outputs": [],
    })
    assert errors == []


def test_validate_test_output_bad_path_in_outputs():
    errors = validate_test_output({
        "agent": "qa-api-test",
        "status": "passed",
        "outputs": [{"path": "tests/wrong-cat/auth/test_login.py"}],
    })
    assert any("path_regex_violation" in e for e in errors)


def test_validate_expected_files_ok():
    errors = validate_expected_files([
        {"path": "tests/api/auth/test_login.py", "covers": ["POST /api/login"]},
    ])
    assert errors == []


def test_validate_expected_files_empty_covers():
    errors = validate_expected_files([
        {"path": "tests/api/auth/test_login.py", "covers": []},
    ])
    assert any("covers_empty_or_not_array" in e for e in errors)


def test_validate_expected_files_null_covers_entry():
    errors = validate_expected_files([
        {"path": "tests/api/auth/test_login.py", "covers": [None]},
    ])
    assert any("covers[0]_empty_or_not_string" in e for e in errors)
