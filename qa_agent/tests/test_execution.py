"""Execution layer tests — process manager, install planner, executor dispatch."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from qa_agent.agent.execution_controller import _pick_executor, execute_all
from qa_agent.executors.ts_reporter import parse_jest_style_json
from qa_agent.executors.maven_runner import _parse as _parse_maven
from qa_agent.executors.pytest_runner import _parse_summary as _parse_pytest
from qa_agent.runtime.install_planner import plan_installs
from qa_agent.runtime.process_manager import run_subprocess
from qa_agent.runtime.workspace import new_workspace
from qa_agent.state import schemas


def test_process_manager_captures_output(tmp_path: Path):
    r = run_subprocess([sys.executable, "-c", "import sys; print('hello'); sys.exit(7)"], cwd=tmp_path, timeout=10)
    assert r.exit_code == 7
    assert "hello" in r.stdout_tail
    assert not r.timed_out


def test_process_manager_kills_on_timeout(tmp_path: Path):
    r = run_subprocess([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout=1)
    assert r.timed_out is True
    assert r.exit_code == -1


def test_workspace_creates_dirs(tmp_path: Path):
    ws = new_workspace(tmp_path)
    assert ws.root.exists()
    assert ws.logs.exists()
    assert ws.artifacts.exists()
    assert (ws.root / "run.json").exists()


def test_install_planner_skips_when_no_tests(tmp_path: Path):
    pm = schemas.ProjectMap(project_root=str(tmp_path), scanned_at=datetime.now(timezone.utc))
    tests = schemas.GeneratedTests(built_at=datetime.now(timezone.utc))
    assert plan_installs(pm, tests) == []


def test_install_planner_plans_pytest_only(tmp_path: Path):
    pm = schemas.ProjectMap(
        project_root=str(tmp_path),
        scanned_at=datetime.now(timezone.utc),
        package_managers=["pip"],
    )
    tests = schemas.GeneratedTests(
        built_at=datetime.now(timezone.utc),
        entries=[
            schemas.GeneratedTest(
                scenario_id="x",
                feature_id="f",
                category="api",
                path="t.py",
                framework="pytest",
                language="python",
            )
        ],
    )
    steps = plan_installs(pm, tests)
    assert len(steps) == 1
    assert steps[0].manager == "pip"
    assert "pytest" in steps[0].args


def test_pytest_summary_parse():
    out = "..F.\n5 failed, 12 passed, 1 skipped in 2.3s"
    assert _parse_pytest(out) == (12, 5, 1)


def test_jest_json_parse(tmp_path: Path):
    out = '... before junk\n{"numPassedTests": 4, "numFailedTests": 1, "numPendingTests": 2}'
    passed, failed, skipped, _ = parse_jest_style_json(out, tmp_path)
    assert (passed, failed, skipped) == (4, 1, 2)


def test_maven_summary_parse():
    out = "Tests run: 10, Failures: 1, Errors: 1, Skipped: 2"
    assert _parse_maven(out) == (6, 2, 2)


def test_pick_executor_dispatches_correctly():
    assert _pick_executor("pytest", "api").__class__.__name__ == "PytestRunner"
    assert _pick_executor("jest", "api").__class__.__name__ == "JestRunner"
    assert _pick_executor("playwright", "ui").__class__.__name__ == "PlaywrightRunner"
    assert _pick_executor("playwright", "accessibility").__class__.__name__ == "A11yRunner"
    assert _pick_executor("pytest", "security").__class__.__name__ == "SecurityRunner"
    assert _pick_executor("unknown", "api") is None


def test_execute_all_skips_when_no_executor_available(tmp_path: Path):
    tests = schemas.GeneratedTests(
        built_at=datetime.now(timezone.utc),
        entries=[
            schemas.GeneratedTest(
                scenario_id="x",
                feature_id="f",
                category="api",
                path="t.unknown",
                framework="unknown",
                language="unknown",
            )
        ],
    )
    results = execute_all(tmp_path, tests, run_id="r1")
    assert results == []
