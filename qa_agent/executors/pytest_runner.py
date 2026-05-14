"""pytest executor — parses ``--junit-xml`` for deterministic per-test results."""

from __future__ import annotations

import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ..runtime.process_manager import run_subprocess
from .base import Executor, ExecutionResult, PerTestRecord, extract_scenario_id


class PytestRunner(Executor):
    framework = "pytest"
    category = "api"

    def available(self, project_root: Path) -> bool:
        return shutil.which("pytest") is not None or shutil.which("python") is not None

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
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            junit_path = Path(f.name)
        try:
            cmd = self._command(test_files, junit_path)
            proc = run_subprocess(cmd, cwd=project_root, timeout=timeout)
            passed, failed, skipped, records = _parse_junit(junit_path, project_root)
            if (passed + failed + skipped) == 0:
                # JUnit XML not produced (e.g. install failure). Fall
                # back to summary line so the counts aren't all zero.
                passed, failed, skipped = _parse_summary(proc.stdout_tail + "\n" + proc.stderr_tail)
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
        finally:
            try:
                junit_path.unlink()
            except OSError:
                pass

    def _command(self, files: list[str], junit_path: Path) -> list[str]:
        base = ["pytest"] if shutil.which("pytest") else ["python", "-m", "pytest"]
        return [*base, "-q", "--tb=short", f"--junit-xml={junit_path}", *files]


def _parse_junit(
    junit_path: Path,
    project_root: Path,
) -> tuple[int, int, int, list[PerTestRecord]]:
    if not junit_path.exists() or junit_path.stat().st_size == 0:
        return 0, 0, 0, []
    try:
        tree = ET.parse(junit_path)
    except ET.ParseError:
        return 0, 0, 0, []
    root = tree.getroot()
    records: list[PerTestRecord] = []
    passed = failed = skipped = 0
    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        file_attr = case.get("file", "")
        duration = float(case.get("time") or 0.0) * 1000.0
        err_node = case.find("failure") or case.find("error")
        skip_node = case.find("skipped")
        status = "passed"
        err_msg = ""
        err_stack = ""
        if err_node is not None:
            status = "failed"
            err_msg = err_node.get("message") or ""
            err_stack = (err_node.text or "").strip()
            failed += 1
        elif skip_node is not None:
            status = "skipped"
            skipped += 1
        else:
            passed += 1
        rel_file = _rel(file_attr or classname, project_root)
        scenario_id = extract_scenario_id(name) or extract_scenario_id(classname)
        test_id = scenario_id or f"{rel_file}::{classname}.{name}"
        records.append(
            PerTestRecord(
                test_id=test_id,
                file=rel_file,
                title=name or classname,
                status=status,
                duration_ms=duration,
                error_message=err_msg,
                error_stack=err_stack,
            )
        )
    return passed, failed, skipped, records


def _rel(path: str, project_root: Path) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(project_root.resolve()))
    except (ValueError, OSError):
        return path


def _parse_summary(text: str) -> tuple[int, int, int]:
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
