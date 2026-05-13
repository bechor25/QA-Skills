"""Common executor interface + result schema + per-test log persistence."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..runtime.process_manager import ProcessResult


@dataclass(slots=True)
class PerTestRecord:
    """Single test outcome captured from a runner reporter.

    Populated by each framework executor and persisted as a small log
    file under ``runs/<id>/logs/`` so the triage agent can read the
    actual error context (assertion message, stack) without having to
    rerun the suite.
    """
    test_id: str         # scenario_id when available, else file::title
    file: str            # repo-relative path
    title: str           # human-readable test title from the runner
    status: str          # passed | failed | skipped | timed_out | other
    duration_ms: float = 0.0
    error_message: str = ""
    error_stack: str = ""


@dataclass(slots=True)
class ExecutionResult:
    """Normalized executor result.

    Subclass executors parse framework-specific output into these fields.
    `process` carries the raw ProcessResult for logs/debug.
    """

    framework: str
    category: str
    test_files: list[str] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    exit_code: int | None = None
    process: ProcessResult | None = None
    per_test_records: list[PerTestRecord] = field(default_factory=list)


class Executor(ABC):
    """Per-framework executor base class."""

    framework: str = ""
    category: str = ""  # primary category — executors may handle several

    @abstractmethod
    def available(self, project_root: Path) -> bool:
        """Return True if the executor can run in this project."""

    @abstractmethod
    def run(self, project_root: Path, test_files: list[str], timeout: int) -> ExecutionResult:
        """Execute the given test files and return a normalized result."""


# ---------------------------------------------------------------------
# Per-test log persistence (shared across runners)
# ---------------------------------------------------------------------

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_\-.:]+")
_MAX_STACK_LEN = 6000


def persist_per_test_logs(
    run_dir: Path,
    result: ExecutionResult,
) -> int:
    """Write a small log file per ``PerTestRecord`` to
    ``<run_dir>/logs/<safe_test_id>.log``. Returns the number of files
    written. Idempotent: re-running overwrites the same files.

    Also writes a per-runner combined log to ``logs/_<framework>-<category>.log``
    holding the tail of stdout/stderr — useful when reporter parsing
    fails entirely.
    """
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for rec in result.per_test_records:
        safe = _safe_filename(rec.test_id)
        target = logs_dir / f"{safe}.log"
        body = _format_record(rec)
        try:
            target.write_text(body, encoding="utf-8")
        except OSError:
            continue
        written += 1

    if result.process is not None:
        combined = logs_dir / f"_{result.framework}-{result.category}.log"
        try:
            combined.write_text(
                "$ "
                + " ".join(result.process.cmd)
                + f"\nexit_code: {result.process.exit_code}\n"
                + f"duration: {result.process.duration_seconds}s\n"
                + "\n=== stdout (tail) ===\n"
                + result.process.stdout_tail
                + "\n=== stderr (tail) ===\n"
                + result.process.stderr_tail,
                encoding="utf-8",
            )
        except OSError:
            pass

    return written


def _safe_filename(s: str) -> str:
    safe = _SAFE_ID_RE.sub("_", s).strip("_")
    return safe[:200] or "unknown"


def _format_record(rec: PerTestRecord) -> str:
    parts = [
        f"test_id: {rec.test_id}",
        f"file: {rec.file}",
        f"title: {rec.title}",
        f"status: {rec.status}",
        f"duration_ms: {rec.duration_ms}",
    ]
    if rec.error_message:
        parts.append("\n=== error message ===\n" + rec.error_message)
    if rec.error_stack:
        stack = rec.error_stack[:_MAX_STACK_LEN]
        if len(rec.error_stack) > _MAX_STACK_LEN:
            stack += f"\n... [{len(rec.error_stack) - _MAX_STACK_LEN} more chars truncated]"
        parts.append("\n=== stack trace ===\n" + stack)
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------
# Shared parsing helpers (jest / vitest share the same JSON shape)
# ---------------------------------------------------------------------

_QA_AGENT_BODY_RE = re.compile(r"QA-AGENT-BODY\s*::\s*([^:]+::[^:]+::[^\s\"']+)")


def extract_scenario_id(title: str) -> str | None:
    """Many of our scaffolds carry the scenario_id inside the test
    title (``QA-AGENT-BODY :: sc::auth::api::01 :: ...``). Return the
    scenario_id if present, else None.
    """
    m = _QA_AGENT_BODY_RE.search(title)
    return m.group(1).strip() if m else None
