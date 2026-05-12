"""Jest executor — uses `--json` for deterministic result parsing."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult


class JestRunner(Executor):
    framework = "jest"
    category = "api"

    def available(self, project_root: Path) -> bool:
        if (project_root / "node_modules" / ".bin" / "jest").exists():
            return True
        return shutil.which("npx") is not None

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        if not test_files:
            return ExecutionResult(framework=self.framework, category=self.category)
        cmd = self._command(project_root, test_files)
        proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
        passed, failed, skipped = _parse_jest_json(proc.stdout_tail)
        # When jest crashes during module resolution / setup, exit_code is
        # non-zero but no tests run (passed=failed=skipped=0). Surface that
        # as a counted failure so the healing engine sees the failure and
        # can act on it instead of treating the run as silent.
        if proc.exit_code not in (0, None) and (passed + failed + skipped) == 0:
            failed = len(test_files)
        return ExecutionResult(
            framework=self.framework,
            category=self.category,
            test_files=test_files,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_seconds=proc.duration_seconds,
            exit_code=proc.exit_code,
            process=proc,
        )

    def _command(self, project_root: Path, files: list[str]) -> list[str]:
        # Prefer the qa-agent jest config (ts-jest preset) if present so
        # TS tests run regardless of the project's own jest setup.
        config = project_root / "jest.qa-agent.config.cjs"
        local = project_root / "node_modules" / ".bin" / "jest"
        base = [str(local)] if local.exists() else ["npx", "--yes", "jest"]
        if config.exists():
            base += ["--config", str(config)]
        return [*base, "--json", "--passWithNoTests", *files]


def _parse_jest_json(text: str) -> tuple[int, int, int]:
    # Jest --json prints a single JSON blob to stdout. Find the first
    # `{` and try to load up to the matching close.
    start = text.find("{")
    if start == -1:
        return 0, 0, 0
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        # Fallback: just look for summary counters Jest prints.
        return 0, 0, 0
    passed = int(data.get("numPassedTests", 0))
    failed = int(data.get("numFailedTests", 0))
    skipped = int(data.get("numPendingTests", 0))
    return passed, failed, skipped
