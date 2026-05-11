"""runner tests — detect_runner, parsers, files resolution (C3.a)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.runner import (
    _resolve_files_from_agent_output,
    detect_runner,
    run_tests,
)


# ---------- detect_runner ----------


def test_detect_pytest_when_python_with_config(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    assert detect_runner(tmp_path, "python", "unit") == "pytest"


def test_detect_pytest_when_python_without_config(tmp_path: Path):
    """Python defaults to pytest even without config."""
    assert detect_runner(tmp_path, "python", "unit") == "pytest"


def test_detect_vitest_via_config(tmp_path: Path):
    (tmp_path / "vitest.config.ts").write_text("export default {}", encoding="utf-8")
    assert detect_runner(tmp_path, "typescript", "unit") == "vitest"


def test_detect_jest_via_config(tmp_path: Path):
    (tmp_path / "jest.config.js").write_text("module.exports = {}", encoding="utf-8")
    assert detect_runner(tmp_path, "typescript", "unit") == "jest"


def test_detect_vitest_via_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"vitest":"^1.0.0"}}', encoding="utf-8"
    )
    assert detect_runner(tmp_path, "typescript", "unit") == "vitest"


def test_detect_jest_via_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"devDependencies":{"jest":"^29.0.0"}}', encoding="utf-8"
    )
    assert detect_runner(tmp_path, "typescript", "unit") == "jest"


def test_detect_unknown_when_typescript_no_signals(tmp_path: Path):
    assert detect_runner(tmp_path, "typescript", "unit") == "unknown"


def test_detect_playwright_for_ui_category(tmp_path: Path):
    (tmp_path / "playwright.config.ts").write_text("export default {}", encoding="utf-8")
    assert detect_runner(tmp_path, "typescript", "ui") == "playwright"


def test_detect_unknown_for_ui_without_playwright_config(tmp_path: Path):
    """ui without playwright config cannot be executed."""
    (tmp_path / "vitest.config.ts").write_text("export default {}", encoding="utf-8")
    assert detect_runner(tmp_path, "typescript", "ui") == "unknown"


def test_detect_playwright_for_a11y_category(tmp_path: Path):
    (tmp_path / "playwright.config.ts").write_text("export default {}", encoding="utf-8")
    assert detect_runner(tmp_path, "typescript", "a11y") == "playwright"


def test_detect_vitest_preferred_over_jest(tmp_path: Path):
    (tmp_path / "vitest.config.ts").write_text("export default {}", encoding="utf-8")
    (tmp_path / "jest.config.js").write_text("module.exports = {}", encoding="utf-8")
    assert detect_runner(tmp_path, "typescript", "unit") == "vitest"


# ---------- _resolve_files_from_agent_output ----------


def test_resolve_files_from_outputs_list():
    paths = _resolve_files_from_agent_output(
        {"outputs": [{"path": "tests/api/auth/test_login.py"},
                     {"path": "tests/api/users/test_users.py"}]}
    )
    assert paths == [
        "tests/api/auth/test_login.py",
        "tests/api/users/test_users.py",
    ]


def test_resolve_files_from_files_array():
    paths = _resolve_files_from_agent_output(
        {"files": ["tests/unit/svc/test_svc.py"]}
    )
    assert paths == ["tests/unit/svc/test_svc.py"]


def test_resolve_files_from_bare_list():
    assert _resolve_files_from_agent_output(["a", "b", 123]) == ["a", "b"]


def test_resolve_files_ignores_malformed():
    assert _resolve_files_from_agent_output({"outputs": [None, {"path": 5}, {"path": "ok"}]}) == ["ok"]


def test_resolve_files_empty_when_unknown_shape():
    assert _resolve_files_from_agent_output({"random": "junk"}) == []


# ---------- run_tests basic shape contract ----------


def test_run_tests_returns_canonical_shape_when_no_files(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    result = run_tests("unit", tmp_path, [], "python")
    for key in ("category", "runner", "total", "passed", "failed", "skipped",
                "duration_ms", "failures", "exit_code"):
        assert key in result, f"missing key {key}"
    assert result["total"] == 0
    assert result["exit_code"] == 0
    assert result.get("note") == "no_files_to_run"


def test_run_tests_unknown_runner_when_typescript_bare(tmp_path: Path):
    result = run_tests("unit", tmp_path, ["tests/unit/svc.test.ts"], "typescript")
    assert result["runner"] == "unknown"
    assert result["exit_code"] == 127
    assert "runner_unknown" in result.get("note", "")


def test_run_tests_categorical_label_set(tmp_path: Path):
    """`category` field must echo the input."""
    result = run_tests("api", tmp_path, [], "python")
    assert result["category"] == "api"
