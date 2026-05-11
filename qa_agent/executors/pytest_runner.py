"""pytest executor — parses `pytest -q --tb=short` output for counts."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult

_SUMMARY_RE = re.compile(
    r"(?:(\d+)\s+failed)?[,\s]*(?:(\d+)\s+passed)?[,\s]*(?:(\d+)\s+skipped)?"
)


class PytestRunner(Executor):
    framework = "pytest"
    category = "api"

    def available(self, project_root: Path) -> bool:
        return shutil.which("pytest") is not None or shutil.which("python") is not None

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        if not test_files:
            return ExecutionResult(framework=self.framework, category=self.category)
        cmd = self._command(test_files)
        proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
        passed, failed, skipped = _parse_summary(proc.stdout_tail + "\n" + proc.stderr_tail)
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

    def _command(self, files: list[str]) -> list[str]:
        if shutil.which("pytest"):
            return ["pytest", "-q", "--tb=short", *files]
        return ["python", "-m", "pytest", "-q", "--tb=short", *files]


def _parse_summary(text: str) -> tuple[int, int, int]:
    # Look for the last summary-shaped line containing passed/failed/skipped.
    passed = failed = skipped = 0
    for line in reversed(text.splitlines()):
        if "passed" in line or "failed" in line or "skipped" in line:
            m_passed = re.search(r"(\d+)\s+passed", line)
            m_failed = re.search(r"(\d+)\s+failed", line)
            m_skipped = re.search(r"(\d+)\s+skipped", line)
            if m_passed or m_failed or m_skipped:
                passed = int(m_passed.group(1)) if m_passed else 0
                failed = int(m_failed.group(1)) if m_failed else 0
                skipped = int(m_skipped.group(1)) if m_skipped else 0
                return passed, failed, skipped
    return 0, 0, 0
