"""Vitest executor — same JSON shape as jest, different binary.

The reporter's full payload is written to a per-run temp file via
``--outputFile`` so we never hit the stdout tail buffer (a large
batch of api tests can produce 500 KB+ of JSON, dwarfing the 256 KB
process-manager tail).
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult
from .ts_reporter import parse_jest_style_json_file


class VitestRunner(Executor):
    framework = "vitest"
    category = "api"

    def available(self, project_root: Path) -> bool:
        if (project_root / "node_modules" / ".bin" / "vitest").exists():
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
        # Use the qa-agent vitest config so the test glob is scoped to
        # tests/qa-agent/. Without it, vitest may pick up the project's
        # own config and run unrelated suites.
        config = project_root / "tests" / "qa-agent" / "vitest.config.ts"
        local = project_root / "node_modules" / ".bin" / "vitest"
        base = [str(local)] if local.exists() else ["npx", "--yes", "vitest"]
        cmd = [
            *base,
            "run",
            "--reporter=json",
            f"--outputFile={report_file}",
            "--passWithNoTests",
        ]
        if config.exists():
            cmd += ["--config", str(config)]
        # vitest expects test paths relative to the config root; the
        # `run` subcommand accepts absolute or relative file args.
        cmd.extend(files)
        return cmd


def _tmp_report_path(project_root: Path) -> Path:
    base = project_root / ".qa-agent" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"vitest-{uuid.uuid4().hex}.json"


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
