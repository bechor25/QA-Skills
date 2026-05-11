"""Common executor interface + result schema."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..runtime.process_manager import ProcessResult


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
