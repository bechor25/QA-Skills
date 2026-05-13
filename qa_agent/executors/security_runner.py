"""Security executor.

The security category piggy-backs on whichever runner the project
uses for its API tests. This wrapper dispatches:

  * ``.py`` files → pytest runner
  * ``.ts`` / ``.js`` files → vitest runner OR jest runner, picked by
    sniffing the file's test-framework import line (``from "vitest"``
    vs ``from "@jest/globals"``).

Future security-only tooling (semgrep, zap-baseline) can plug in here
without touching the rest of the pipeline.
"""

from __future__ import annotations

from pathlib import Path

from .base import Executor, ExecutionResult
from .jest_runner import JestRunner
from .pytest_runner import PytestRunner
from .vitest_runner import VitestRunner


class SecurityRunner(Executor):
    framework = "security"
    category = "security"

    def __init__(self) -> None:
        self._py = PytestRunner()
        self._jest = JestRunner()
        self._vitest = VitestRunner()

    def available(self, project_root: Path) -> bool:
        return (
            self._py.available(project_root)
            or self._vitest.available(project_root)
            or self._jest.available(project_root)
        )

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        py = [t for t in test_files if t.endswith(".py")]
        ts = [t for t in test_files if t.endswith((".ts", ".tsx", ".js"))]
        results: list[ExecutionResult] = []
        if py and self._py.available(project_root):
            results.append(self._py.run(project_root, py, timeout))
        if ts:
            runner = self._pick_ts_runner(project_root, ts)
            if runner.available(project_root):
                results.append(runner.run(project_root, ts, timeout))

        if not results:
            return ExecutionResult(framework=self.framework, category=self.category)
        merged_records = []
        for r in results:
            merged_records.extend(r.per_test_records)
        merged = ExecutionResult(
            framework=self.framework,
            category=self.category,
            test_files=test_files,
            passed=sum(r.passed for r in results),
            failed=sum(r.failed for r in results),
            skipped=sum(r.skipped for r in results),
            duration_seconds=sum(r.duration_seconds for r in results),
            exit_code=max((r.exit_code or 0) for r in results),
            process=results[-1].process,
            per_test_records=merged_records,
        )
        return merged

    def _pick_ts_runner(self, project_root: Path, files: list[str]) -> Executor:
        """Sniff a sample test file's imports to pick the runner. The
        scaffold generator emits exactly one of these import lines per
        file, so a single peek is enough.
        """
        for f in files:
            try:
                text = (project_root / f).read_text(encoding="utf-8")
            except OSError:
                continue
            if 'from "vitest"' in text or "from 'vitest'" in text:
                return self._vitest
            if "@jest/globals" in text:
                return self._jest
        # Default to vitest — modern, runs TS natively.
        return self._vitest
