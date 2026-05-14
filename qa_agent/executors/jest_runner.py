"""Jest executor — uses ``--json`` + ``--outputFile`` for deterministic
result parsing without depending on the stdout tail buffer."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult
from .ts_reporter import parse_jest_style_json_file


class JestRunner(Executor):
    framework = "jest"
    category = "api"

    def available(self, project_root: Path) -> bool:
        if (project_root / "node_modules" / ".bin" / "jest").exists():
            return True
        return shutil.which("npx") is not None

    def run(
        self,
        project_root: Path,
        test_files: list[str],
        timeout: int,
        category: str | None = None,
    ) -> ExecutionResult:
        effective_category = category or self.category
        if not test_files:
            return ExecutionResult(framework=self.framework, category=effective_category)
        report_file = _tmp_report_path(project_root)
        cmd = self._command(project_root, test_files, report_file)
        try:
            proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
            passed, failed, skipped, records = parse_jest_style_json_file(
                report_file, project_root, fallback_stdout=proc.stdout_tail
            )
        finally:
            _safe_unlink(report_file)
        # When the runner crashes during module resolution / setup,
        # exit_code is non-zero but no tests run. Surface that as a
        # counted failure so the healing engine sees it.
        if proc.exit_code not in (0, None) and (passed + failed + skipped) == 0:
            failed = len(test_files)
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
            per_test_records=records,
        )

    def _command(self, project_root: Path, files: list[str], report_file: Path) -> list[str]:
        # Prefer the qa-agent jest config (ts-jest preset) if present so
        # TS tests run regardless of the project's own jest setup.
        config = project_root / "jest.qa-agent.config.cjs"
        local = project_root / "node_modules" / ".bin" / "jest"
        base = [str(local)] if local.exists() else ["npx", "--yes", "jest"]
        if config.exists():
            base += ["--config", str(config)]
        return [
            *base,
            "--json",
            f"--outputFile={report_file}",
            "--passWithNoTests",
            *files,
        ]


def _tmp_report_path(project_root: Path) -> Path:
    base = project_root / ".qa-agent" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"jest-{uuid.uuid4().hex}.json"


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
