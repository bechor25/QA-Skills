"""Gradle test executor — `./gradlew test` (or `gradle test`)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult

_SUMMARY_RE = re.compile(
    r"(\d+)\s+tests\s+completed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+skipped)?",
    re.IGNORECASE,
)


class GradleRunner(Executor):
    framework = "gradle"
    category = "api"

    def available(self, project_root: Path) -> bool:
        if (project_root / "gradlew").exists():
            return True
        return shutil.which("gradle") is not None

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        wrapper = project_root / "gradlew"
        cmd = [str(wrapper), "test"] if wrapper.exists() else ["gradle", "test"]
        proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
        passed, failed, skipped = _parse(proc.stdout_tail + proc.stderr_tail)
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


def _parse(text: str) -> tuple[int, int, int]:
    last = None
    for m in _SUMMARY_RE.finditer(text):
        last = m
    if not last:
        return 0, 0, 0
    total = int(last.group(1))
    failed = int(last.group(2))
    skipped = int(last.group(3) or 0)
    return max(total - failed - skipped, 0), failed, skipped
