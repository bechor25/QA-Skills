"""Flaky / healing / retry-engine tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from qa_agent.agent.retry_engine import _failed, _flaky, scope_paths
from qa_agent.flaky.classifier import classify
from qa_agent.flaky.detector import _failed_paths
from qa_agent.healing.classifiers import classify_failure
from qa_agent.healing.engine import _bump_timeout, _inject_wait, heal_failures
from qa_agent.healing.policies import pick_action
from qa_agent.state import schemas
from qa_agent.state.manager import StateManager


def test_flaky_classifier_buckets():
    assert classify("Timeout: exceeded 30000ms") == "timing"
    assert classify("Connection refused: ECONNRESET") == "network"
    assert classify("ENV not set: missing env DATABASE_URL") == "env"
    assert classify("race condition in concurrently-modified state") == "race"
    assert classify("fixture not found; depends on previous setup") == "order"


def test_healing_classifier_buckets():
    assert classify_failure("Locator(.foo) not found") == "selector"
    assert classify_failure("Timed out waiting") == "timeout"
    assert classify_failure("ModuleNotFoundError: No module named 'foo'") == "missing-dependency"
    assert classify_failure("401 Unauthorized") == "auth"
    assert classify_failure("AssertionError: expected 'x' to equal 'y'") == "assertion"
    assert classify_failure("totally novel") == "unknown"


def test_policy_never_weakens_assertions():
    assert pick_action("assertion") == "manual"


def test_inject_wait_into_playwright(tmp_path: Path):
    p = tmp_path / "t.ts"
    p.write_text(
        'import { test, expect } from "@playwright/test";\n'
        'test("x", async ({ page }) => {\n'
        '  await page.goto("/");\n'
        '  await expect(page.getByRole("main")).toBeVisible();\n'
        '});\n',
        encoding="utf-8",
    )
    assert _inject_wait(p)
    assert "waitForLoadState" in p.read_text(encoding="utf-8")


def test_bump_timeout(tmp_path: Path):
    p = tmp_path / "t.ts"
    p.write_text(
        'test("x", async ({ page }) => { await expect(x).toBeVisible({ timeout: 1000 }); });\n',
        encoding="utf-8",
    )
    assert _bump_timeout(p)
    assert "timeout: 2000" in p.read_text(encoding="utf-8")


def test_heal_failures_marks_categories(tmp_path: Path):
    p = tmp_path / "t.py"
    p.write_text("def test_x(): assert True\n", encoding="utf-8")
    attempts = heal_failures(
        tmp_path,
        [("t.py", "AssertionError: expected x to equal y")],
    )
    assert attempts[0].failure_category == "assertion"
    assert attempts[0].action == "manual"
    assert attempts[0].applied is False


def test_retry_engine_failed_scope(tmp_path: Path):
    sm = StateManager(str(tmp_path))
    sm.save(
        schemas.GeneratedTests(
            built_at=datetime.now(timezone.utc),
            entries=[
                schemas.GeneratedTest(
                    scenario_id="a",
                    feature_id="f",
                    category="api",
                    path="a.py",
                    framework="pytest",
                    language="python",
                ),
                schemas.GeneratedTest(
                    scenario_id="b",
                    feature_id="f",
                    category="api",
                    path="b.py",
                    framework="pytest",
                    language="python",
                ),
            ],
        )
    )
    sm.save(
        schemas.ExecutionHistory(
            records=[
                schemas.ExecutionRecord(
                    run_id="r1",
                    started_at=datetime.now(timezone.utc),
                    category="api",
                    test_files=["a.py", "b.py"],
                    passed=1,
                    failed=1,
                )
            ]
        )
    )
    paths = scope_paths(tmp_path, "failed")
    assert paths == ["a.py", "b.py"]


def test_failed_paths_only_last_run():
    h = schemas.ExecutionHistory(
        records=[
            schemas.ExecutionRecord(
                run_id="old",
                started_at=datetime.now(timezone.utc),
                category="api",
                test_files=["old.py"],
                failed=1,
            ),
            schemas.ExecutionRecord(
                run_id="new",
                started_at=datetime.now(timezone.utc),
                category="api",
                test_files=["new.py"],
                failed=1,
            ),
        ]
    )
    assert _failed_paths(h) == {"new.py"}
