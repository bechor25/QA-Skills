"""Security executor.

For now the security category runs alongside the API/UI executors —
security tests live as pytest or Playwright files. This wrapper exists
so the controller can request `category="security"` explicitly and so
future tooling (semgrep / zap-baseline) can plug in here without
disturbing the rest of the system.
"""

from __future__ import annotations

from pathlib import Path

from .base import Executor, ExecutionResult
from .pytest_runner import PytestRunner
from .playwright_runner import PlaywrightRunner


class SecurityRunner(Executor):
    framework = "security"
    category = "security"

    def __init__(self) -> None:
        self._py = PytestRunner()
        self._pw = PlaywrightRunner()

    def available(self, project_root: Path) -> bool:
        return self._py.available(project_root) or self._pw.available(project_root)

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        py = [t for t in test_files if t.endswith(".py")]
        ts = [t for t in test_files if t.endswith((".ts", ".tsx", ".js"))]
        results = []
        if py and self._py.available(project_root):
            results.append(self._py.run(project_root, py, timeout))
        if ts and self._pw.available(project_root):
            results.append(self._pw.run(project_root, ts, timeout))

        if not results:
            return ExecutionResult(framework=self.framework, category=self.category)
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
        )
        return merged
