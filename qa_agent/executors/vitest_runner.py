"""Vitest executor — same JSON shape as jest, different binary."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult
from .ts_reporter import parse_jest_style_json


class VitestRunner(Executor):
    framework = "vitest"
    category = "api"

    def available(self, project_root: Path) -> bool:
        if (project_root / "node_modules" / ".bin" / "vitest").exists():
            return True
        return shutil.which("npx") is not None

    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        if not test_files:
            return ExecutionResult(framework=self.framework, category=self.category)
        cmd = self._command(project_root, test_files)
        proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
        passed, failed, skipped, records = parse_jest_style_json(proc.stdout_tail, project_root)
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
            per_test_records=records,
        )

    def _command(self, project_root: Path, files: list[str]) -> list[str]:
        # Use the qa-agent vitest config so the test glob is scoped to
        # tests/qa-agent/. Without it, vitest may pick up the project's
        # own config and run unrelated suites.
        config = project_root / "tests" / "qa-agent" / "vitest.config.ts"
        local = project_root / "node_modules" / ".bin" / "vitest"
        base = [str(local)] if local.exists() else ["npx", "--yes", "vitest"]
        cmd = [*base, "run", "--reporter=json", "--passWithNoTests"]
        if config.exists():
            cmd += ["--config", str(config)]
        # vitest expects test paths relative to the config root; the
        # `run` subcommand accepts absolute or relative file args.
        cmd.extend(files)
        return cmd
