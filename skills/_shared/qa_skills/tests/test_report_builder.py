"""report_builder smoke tests — ensure assembly produces valid report-data shape."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_skills.analysis import load_analysis
from qa_skills.report_builder import build_report_data, REPORT_DATA_VERSION


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fastapi():
    return load_analysis(FIXTURES / "python_fastapi_analysis.json")


def _make_outputs():
    return [
        {"agent": "qa-unit-test", "status": "passed", "outputs": [
            {"path": "tests/unit/auth/test_auth.py", "covers": ["app/auth.py"], "tests_written": 5},
            {"path": "tests/unit/users/test_users.py", "covers": ["app/users.py"], "tests_written": 4},
        ]},
        {"agent": "qa-api-test", "status": "passed", "outputs": [
            {"path": "tests/api/auth/test_login.py", "covers": ["POST /api/login"], "tests_written": 7},
        ]},
    ]


def test_minimal_build_produces_valid_shape(fastapi, tmp_path):
    report = build_report_data(
        run_id="run-1", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=_make_outputs(),
        env_categories_removed=[], locale="en",
    )
    assert report["version"] == REPORT_DATA_VERSION
    assert report["run_id"] == "run-1"
    assert report["language"] == "python"
    assert isinstance(report["coverage_by_category"], dict)
    assert "unit" in report["coverage_by_category"]
    assert "api" in report["coverage_by_category"]


def test_quality_score_present_and_in_range(fastapi, tmp_path):
    report = build_report_data(
        run_id="run-2", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=_make_outputs(),
        env_categories_removed=[],
    )
    assert 0 <= report["quality_score"] <= 100


def test_env_removed_carries_reason(fastapi, tmp_path):
    report = build_report_data(
        run_id="run-3", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=_make_outputs(),
        env_categories_removed=[{"name": "ui", "reason": "no_playwright", "action": "install"}],
    )
    ui = report["coverage_by_category"]["ui"]
    assert ui["status"] == "skipped:env_removed"
    assert ui["reason"] == "no_playwright"


def test_legacy_status_normalized(fastapi, tmp_path):
    """Pre-refactor agents returning skipped_no_server → normalized to skipped:no_server."""
    outputs = [
        {"agent": "qa-ui-test", "status": "skipped_no_server", "outputs": []},
    ]
    report = build_report_data(
        run_id="run-4", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=outputs,
        env_categories_removed=[],
    )
    assert report["coverage_by_category"]["ui"]["status"] == "skipped:no_server"


def test_phantom_routes_filtered_in_coverage(fastapi, tmp_path):
    outputs = [
        {"agent": "qa-api-test", "status": "passed", "outputs": [
            {"path": "tests/api/auth/test_login.py",
             "covers": ["POST /api/login", "POST /api/nonexistent"],
             "tests_written": 7},
        ]},
    ]
    report = build_report_data(
        run_id="run-5", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=outputs,
        env_categories_removed=[],
    )
    api_cov = report["coverage_by_category"]["api"]
    assert "POST /api/login" in api_cov["covered_items"]
    assert "POST /api/nonexistent" not in api_cov["covered_items"]


def test_coverage_includes_execution_block_default_shape(fastapi, tmp_path):
    """Every coverage entry MUST have an execution block (default = empty)."""
    report = build_report_data(
        run_id="run-x1", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=_make_outputs(),
        env_categories_removed=[],
    )
    for cat, info in report["coverage_by_category"].items():
        assert "execution" in info, f"{cat} missing execution block"
        execu = info["execution"]
        for k in ("runner", "total", "passed", "failed", "skipped",
                  "duration_ms", "failures", "exit_code"):
            assert k in execu, f"{cat}.execution missing {k}"


def test_execution_results_dict_threaded_into_coverage(fastapi, tmp_path):
    execution_results = {
        "qa-api-test": {
            "category": "api", "runner": "vitest",
            "total": 5, "passed": 3, "failed": 2, "skipped": 0,
            "duration_ms": 700,
            "failures": [{"file": "tests/api/auth/test_login.py",
                          "title": "login 401 path",
                          "error": "AssertionError",
                          "stack_excerpt": ""}],
            "exit_code": 1,
        },
    }
    report = build_report_data(
        run_id="run-x2", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=_make_outputs(),
        env_categories_removed=[],
        execution_results=execution_results,
    )
    api = report["coverage_by_category"]["api"]
    assert api["execution"]["failed"] == 2
    assert api["execution"]["runner"] == "vitest"
    # Status downgraded to partial because failures > 0
    assert api["status"] == "partial"


def test_runner_missing_marks_skipped(fastapi, tmp_path):
    execution_results = {
        "qa-unit-test": {
            "runner": "unknown", "total": 0, "passed": 0, "failed": 0,
            "skipped": 0, "duration_ms": 0, "failures": [], "exit_code": 127,
        },
    }
    report = build_report_data(
        run_id="run-x3", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=_make_outputs(),
        env_categories_removed=[],
        execution_results=execution_results,
    )
    unit = report["coverage_by_category"]["unit"]
    assert unit["status"] == "skipped:runner_missing"


def test_embedded_execution_result_takes_precedence(fastapi, tmp_path):
    """When the agent embeds execution_result in its AgentResult, it wins."""
    outputs = [
        {"agent": "qa-api-test", "status": "passed", "outputs": [
            {"path": "tests/api/auth/test_login.py", "covers": ["POST /api/login"], "tests_written": 7},
        ],
         "execution_result": {
             "runner": "vitest", "total": 1, "passed": 1, "failed": 0,
             "skipped": 0, "duration_ms": 50, "failures": [], "exit_code": 0,
         }},
    ]
    # logs-dir style results would say "failed: 99" — embedded should win.
    execution_results = {
        "qa-api-test": {"runner": "vitest", "total": 1, "passed": 0, "failed": 99,
                        "skipped": 0, "duration_ms": 0, "failures": [], "exit_code": 1},
    }
    report = build_report_data(
        run_id="run-x4", project_root=str(tmp_path),
        analysis=fastapi, all_test_outputs=outputs,
        env_categories_removed=[],
        execution_results=execution_results,
    )
    api = report["coverage_by_category"]["api"]
    assert api["execution"]["failed"] == 0   # embedded wins
    assert api["execution"]["passed"] == 1


def test_gaps_identify_uncovered_payment_module(tmp_path):
    """Modify analysis to include a payments module and confirm it surfaces as high-severity gap."""
    import json
    src = json.loads((FIXTURES / "python_fastapi_analysis.json").read_text())
    src["modules"].append({
        "path": "app/payments/charge.py", "hash": "p1", "type": "service",
        "has_auth": False, "has_db_queries": False, "input_fields": [],
    })
    tmp_analysis = tmp_path / "analysis.json"
    tmp_analysis.write_text(json.dumps(src), encoding="utf-8")

    from qa_skills.analysis import load_analysis as ll
    a = ll(tmp_analysis)

    report = build_report_data(
        run_id="run-6", project_root=str(tmp_path),
        analysis=a, all_test_outputs=[], env_categories_removed=[],
    )
    high = [g for g in report["gaps"] if g["severity"] == "high"]
    assert any("app/payments/charge.py" in g["path"] for g in high)
