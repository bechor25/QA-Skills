"""validators tests — path regex, AgentResult shape, expected_files."""

from __future__ import annotations

from qa_skills.validators import (
    PY_PATH_REGEX,
    TS_PATH_REGEX,
    language_pattern,
    validate_agent_result_against_contract,
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


# --- A4: language-aware path regex ----------------------------------------


def test_ts_project_rejects_python_prefix_name():
    ok, err = validate_path(
        "tests/api/auth/test_login.api.test.ts", language="typescript"
    )
    assert not ok
    assert "path_regex_violation_typescript" in err


def test_ts_project_accepts_dot_test_name():
    ok, _ = validate_path(
        "tests/api/auth/login.api.test.ts", language="typescript"
    )
    assert ok


def test_python_project_accepts_test_prefix():
    ok, _ = validate_path("tests/api/auth/test_login.py", language="python")
    assert ok


def test_python_project_rejects_dot_test_name():
    ok, err = validate_path(
        "tests/api/auth/login.test.py", language="python"
    )
    assert not ok
    assert "path_regex_violation_python" in err


def test_ts_project_rejects_python_unit_file():
    ok, _ = validate_path(
        "tests/unit/services/test_user_service.py", language="typescript"
    )
    assert not ok


def test_python_project_rejects_ts_file():
    ok, _ = validate_path(
        "tests/unit/services/user_service.spec.ts", language="python"
    )
    assert not ok


def test_validate_test_output_ts_language_rejects_py_prefix():
    errors = validate_test_output(
        {
            "agent": "qa-api-test",
            "status": "passed",
            "outputs": [{"path": "tests/api/auth/test_login.api.test.ts"}],
        },
        language="typescript",
    )
    assert any("path_regex_violation_typescript" in e for e in errors)


def test_validate_test_output_no_language_back_compat():
    """When language=None, permissive ANY pattern allows either convention."""
    errors = validate_test_output(
        {
            "agent": "qa-api-test",
            "status": "passed",
            "outputs": [
                {"path": "tests/api/auth/test_login.py"},
                {"path": "tests/api/auth/login.api.test.ts"},
            ],
        }
    )
    assert errors == []


def test_language_pattern_returns_python_for_python():
    assert language_pattern("python") == PY_PATH_REGEX.pattern


def test_language_pattern_returns_typescript_for_ts():
    assert language_pattern("typescript") == TS_PATH_REGEX.pattern


def test_language_pattern_unknown_falls_back_to_any():
    """Unknown language returns the permissive union pattern."""
    assert "test_[^/]+\\.py" in language_pattern("rust")


# --- B1: validate_agent_result_against_contract ---------------------------


def test_contract_diff_all_aligned():
    expected = [
        {"path": "tests/api/auth/test_login.py", "covers": ["POST /api/login"]},
        {"path": "tests/api/users/test_users.py", "covers": ["GET /api/users"]},
    ]
    result = {
        "agent": "qa-api-test",
        "status": "passed",
        "outputs": [
            {"path": "tests/api/auth/test_login.py"},
            {"path": "tests/api/users/test_users.py"},
        ],
    }
    diff = validate_agent_result_against_contract(result, expected, language="python")
    assert diff == {"extras": [], "missing": [], "violations": []}


def test_contract_diff_detects_missing():
    expected = [
        {"path": "tests/api/auth/test_login.py", "covers": ["POST /api/login"]},
        {"path": "tests/api/users/test_users.py", "covers": ["GET /api/users"]},
    ]
    result = {
        "agent": "qa-api-test",
        "status": "passed",
        "outputs": [{"path": "tests/api/auth/test_login.py"}],
    }
    diff = validate_agent_result_against_contract(result, expected, language="python")
    assert diff["missing"] == ["tests/api/users/test_users.py"]
    assert diff["extras"] == []


def test_contract_diff_detects_extras_wrong_name():
    """TS project — sub-agent emitted Python-style test_X.ts: extras + violations."""
    expected = [
        {"path": "tests/api/auth/login.api.test.ts", "covers": ["POST /api/login"]},
    ]
    result = {
        "agent": "qa-api-test",
        "status": "passed",
        "outputs": [
            {"path": "tests/api/auth/test_login.api.test.ts"},  # wrong (test_ prefix)
            {"path": "tests/api/auth/login.api.test.ts"},        # right
        ],
    }
    diff = validate_agent_result_against_contract(result, expected, language="typescript")
    assert diff["extras"] == ["tests/api/auth/test_login.api.test.ts"]
    assert diff["missing"] == []
    assert any("path_regex_violation_typescript" in v for v in diff["violations"])


def test_contract_diff_handles_empty_expected():
    """No expected_files supplied — every emitted path becomes 'extras'."""
    result = {"outputs": [{"path": "tests/unit/svc/test_svc.py"}]}
    diff = validate_agent_result_against_contract(result, [], language="python")
    assert diff["extras"] == ["tests/unit/svc/test_svc.py"]
    assert diff["missing"] == []


def test_contract_diff_ignores_malformed_output_entries():
    expected = [{"path": "tests/unit/svc/test_svc.py", "covers": ["app/svc.py"]}]
    result = {
        "outputs": [
            None,
            {"not_path": "x"},
            {"path": 123},
            {"path": ""},
            {"path": "tests/unit/svc/test_svc.py"},
        ],
    }
    diff = validate_agent_result_against_contract(result, expected, language="python")
    assert diff["extras"] == []
    assert diff["missing"] == []
