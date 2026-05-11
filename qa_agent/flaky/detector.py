"""Flaky-test detector.

For every test file that failed in the *latest* execution, re-run it
N times via the dispatcher. If the outcome varies, mark it flaky and
classify the cause.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..agent.execution_controller import _pick_executor
from ..shared.logging import get_logger
from ..state import schemas
from .classifier import classify

log = get_logger("qa_agent.flaky.detector")


def detect_flaky(
    project_root: Path,
    tests: schemas.GeneratedTests,
    history: schemas.ExecutionHistory,
    reruns: int = 3,
    timeout: int = 300,
) -> schemas.FlakyState:
    """Return a FlakyState with one entry per detected flake."""
    failed_paths = _failed_paths(history)
    if not failed_paths:
        log.info("flaky: no failed tests in latest history; nothing to re-run")
        return schemas.FlakyState()

    log.info("flaky: re-running %d failed test file(s) up to %dx", len(failed_paths), reruns)
    test_by_path = {t.path: t for t in tests.entries if t.path in failed_paths}

    entries: list[schemas.FlakyEntry] = []
    for path, test in test_by_path.items():
        executor = _pick_executor(test.framework, test.category)
        if executor is None or not executor.available(project_root):
            continue
        outcomes: list[bool] = []
        last_log = ""
        for _ in range(reruns):
            result = executor.run(project_root, [path], timeout)
            outcomes.append((result.failed == 0) and (result.exit_code == 0))
            if result.process is not None:
                last_log = (result.process.stderr_tail or "") + (result.process.stdout_tail or "")
        passes = sum(1 for ok in outcomes if ok)
        failures = reruns - passes
        if 0 < passes < reruns:
            entries.append(
                schemas.FlakyEntry(
                    test_id=path,
                    classification=classify(last_log),
                    runs=reruns,
                    failures=failures,
                    last_seen=datetime.now(timezone.utc),
                    rationale=f"{passes}/{reruns} passes; logs match {_summary(last_log)}",
                )
            )

    log.info("flaky: %d flake(s) classified", len(entries))
    return schemas.FlakyState(entries=entries)


def _failed_paths(history: schemas.ExecutionHistory) -> set[str]:
    if not history.records:
        return set()
    last_run = history.records[-1].run_id
    out: set[str] = set()
    for rec in reversed(history.records):
        if rec.run_id != last_run:
            break
        if rec.failed:
            out.update(rec.test_files)
    return out


def _summary(text: str) -> str:
    if not text:
        return "no log"
    snippet = text[-200:].replace("\n", " ").strip()
    return f"`{snippet[:120]}…`"
