"""Playwright executor — drives @playwright/test through `npx playwright test`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult


class PlaywrightRunner(Executor):
    framework = "playwright"
    category = "ui"

    def available(self, project_root: Path) -> bool:
        if (project_root / "node_modules" / "@playwright" / "test").exists():
            return True
        return shutil.which("npx") is not None

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        if not test_files:
            return ExecutionResult(framework=self.framework, category=self.category)
        cmd = self._command(project_root, test_files)
        # Playwright's JSON reporter prints to stdout when configured.
        env = {"PLAYWRIGHT_JSON_OUTPUT_NAME": "playwright-report.json"}
        proc = run_subprocess(cmd, cwd=project_root, timeout=timeout, env=env)
        report_file = project_root / "playwright-report.json"
        passed, failed, skipped = _parse_playwright(report_file, proc.stdout_tail)
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
        local = project_root / "node_modules" / ".bin" / "playwright"
        base = [str(local)] if local.exists() else ["npx", "--yes", "playwright"]
        return [*base, "test", "--reporter=json,line", *files]


def _parse_playwright(report_path: Path, stdout: str) -> tuple[int, int, int]:
    text = ""
    if report_path.exists():
        try:
            text = report_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
    if not text:
        text = stdout
    start = text.find("{")
    if start == -1:
        return 0, 0, 0
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        return 0, 0, 0
    stats = data.get("stats") or {}
    return int(stats.get("expected", 0)), int(stats.get("unexpected", 0)), int(stats.get("skipped", 0))
