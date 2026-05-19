"""Playwright executor — drives @playwright/test through `npx playwright test`."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult, PerTestRecord, extract_scenario_id


class PlaywrightRunner(Executor):
    framework = "playwright"
    category = "ui"

    def available(self, project_root: Path) -> bool:
        if (project_root / "node_modules" / "@playwright" / "test").exists():
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
        cmd = self._command(project_root, test_files)
        # Absolute json-output path: Playwright resolves a *relative*
        # PLAYWRIGHT_JSON_OUTPUT_NAME against the config rootDir
        # (tests/qa-agent/), not cwd. An absolute path is honoured
        # verbatim, so we always know where the report lands and never
        # depend on the 256 KB stdout tail (a 30-test report exceeds it,
        # losing the opening brace). Mirrors the vitest --outputFile path.
        report_file = _tmp_report_path(project_root)
        env = {"PLAYWRIGHT_JSON_OUTPUT_NAME": str(report_file)}
        try:
            proc = run_subprocess(cmd, cwd=project_root, timeout=timeout, env=env)
            passed, failed, skipped, records = _parse_playwright(
                report_file, proc.stdout_tail, project_root
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

    def _command(self, project_root: Path, files: list[str]) -> list[str]:
        local = project_root / "node_modules" / ".bin" / "playwright"
        base = [str(local)] if local.exists() else ["npx", "--yes", "playwright"]
        config = project_root / "tests" / "qa-agent" / "playwright.config.ts"
        cmd = [*base, "test", "--reporter=json"]
        if config.exists():
            cmd += ["--config", str(config)]
        cmd.extend(files)
        return cmd


def _parse_playwright(
    report_path: Path,
    stdout: str,
    project_root: Path,
) -> tuple[int, int, int, list[PerTestRecord]]:
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
        return 0, 0, 0, []
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        return 0, 0, 0, []

    stats = data.get("stats") or {}
    passed = int(stats.get("expected", 0))
    failed = int(stats.get("unexpected", 0))
    skipped = int(stats.get("skipped", 0))

    records: list[PerTestRecord] = []
    for suite in data.get("suites", []) or []:
        records.extend(_walk_pw_suite(suite, suite.get("file", ""), project_root))
    return passed, failed, skipped, records


def _walk_pw_suite(suite: dict, file_path: str, project_root: Path) -> list[PerTestRecord]:
    out: list[PerTestRecord] = []
    file_path = suite.get("file", file_path)
    for spec in suite.get("specs", []) or []:
        title = spec.get("title", "")
        spec_file = spec.get("file", file_path)
        for test in spec.get("tests", []) or []:
            for result in test.get("results", []) or []:
                status = (result.get("status") or "").lower()
                duration = float(result.get("duration") or 0.0)
                err = result.get("error") or {}
                err_msg = err.get("message") if isinstance(err, dict) else ""
                err_stack = err.get("stack") if isinstance(err, dict) else ""
                scenario_id = extract_scenario_id(title)
                rel_file = _rel(spec_file, project_root)
                test_id = scenario_id or f"{rel_file}::{title}"
                out.append(
                    PerTestRecord(
                        test_id=test_id,
                        file=rel_file,
                        title=title,
                        status=_normalize_pw_status(status),
                        duration_ms=duration,
                        error_message=err_msg or "",
                        error_stack=err_stack or "",
                    )
                )
    for child in suite.get("suites", []) or []:
        out.extend(_walk_pw_suite(child, file_path, project_root))
    return out


def _normalize_pw_status(s: str) -> str:
    return {
        "passed": "passed",
        "failed": "failed",
        "timedout": "failed",
        "interrupted": "failed",
        "skipped": "skipped",
    }.get(s, s or "other")


def _rel(path: str, project_root: Path) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(project_root.resolve()))
    except (ValueError, OSError):
        return path


def _tmp_report_path(project_root: Path) -> Path:
    base = project_root / ".qa-agent" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"playwright-{uuid.uuid4().hex}.json"


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
