"""Maven Surefire executor — `mvn -q test` and parses summary line."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult

_SUMMARY_RE = re.compile(
    r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)"
)


class MavenRunner(Executor):
    framework = "maven"
    category = "api"

    def available(self, project_root: Path) -> bool:
        return (project_root / "pom.xml").exists() and shutil.which("mvn") is not None

    def run(
        self,
        project_root: Path,
        test_files: list[str],
        timeout: int,
        category: str | None = None,
    ) -> ExecutionResult:
        effective_category = category or self.category
        cmd = ["mvn", "-q", "test"]
        proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
        passed, failed, skipped = _parse(proc.stdout_tail + proc.stderr_tail)
        return ExecutionResult(
            framework=self.framework,
            category=effective_category,
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
    failures = int(last.group(2))
    errors = int(last.group(3))
    skipped = int(last.group(4))
    failed = failures + errors
    passed = max(total - failed - skipped, 0)
    return passed, failed, skipped
