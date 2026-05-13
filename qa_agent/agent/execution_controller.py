"""Execution controller.

Drives the per-category executor matrix:
  - groups GeneratedTests by (framework, category)
  - picks an executor for each group
  - runs them sequentially (parallelism is a Phase 5 concern)
  - persists every run as an ExecutionRecord
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..executors.a11y_runner import A11yRunner
from ..executors.base import Executor, ExecutionResult, persist_per_test_logs
from ..executors.gradle_runner import GradleRunner
from ..executors.jest_runner import JestRunner
from ..executors.maven_runner import MavenRunner
from ..executors.playwright_runner import PlaywrightRunner
from ..executors.pytest_runner import PytestRunner
from ..executors.security_runner import SecurityRunner
from ..executors.vitest_runner import VitestRunner
from ..shared.logging import get_logger
from ..shared.paths import run_dir
from ..state import schemas
from ..state.manager import StateManager

log = get_logger("qa_agent.agent.execution_controller")


def execute_all(
    project_root: Path,
    tests: schemas.GeneratedTests,
    run_id: str,
    timeout: int = 300,
) -> list[ExecutionResult]:
    """Group tests, dispatch to executors, append history. Returns results."""
    sm = StateManager(str(project_root))
    history = sm.execution_history()

    grouped = _group(tests.entries)
    results: list[ExecutionResult] = []
    for (framework, category), paths in grouped.items():
        executor = _pick_executor(framework, category)
        if executor is None or not executor.available(project_root):
            log.warning(
                "execute: no executor for framework=%s category=%s — %d files skipped",
                framework,
                category,
                len(paths),
            )
            continue
        started = datetime.now(timezone.utc)
        log.info("execute: %s/%s — %d files", framework, category, len(paths))
        result = executor.run(project_root, paths, timeout)
        results.append(result)
        written = persist_per_test_logs(run_dir(str(project_root), run_id), result)
        if written:
            log.info(
                "execute: persisted %d per-test logs for %s/%s",
                written, framework, category,
            )
        history.records.append(
            schemas.ExecutionRecord(
                run_id=run_id,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                category=category,
                test_files=paths,
                passed=result.passed,
                failed=result.failed,
                skipped=result.skipped,
                duration_seconds=result.duration_seconds,
                exit_code=result.exit_code,
            )
        )

    sm.save(history)
    return results


def _group(entries: list[schemas.GeneratedTest]) -> dict[tuple[str, str], list[str]]:
    groups: dict[tuple[str, str], list[str]] = {}
    for e in entries:
        groups.setdefault((e.framework, e.category), []).append(e.path)
    return groups


def _pick_executor(framework: str, category: str) -> Executor | None:
    if category == "accessibility" and framework == "playwright":
        return A11yRunner()
    if category == "security":
        return SecurityRunner()
    if framework == "pytest":
        return PytestRunner()
    if framework == "jest":
        return JestRunner()
    if framework == "vitest":
        return VitestRunner()
    if framework == "playwright":
        return PlaywrightRunner()
    if framework == "maven":
        return MavenRunner()
    if framework == "gradle":
        return GradleRunner()
    return None
