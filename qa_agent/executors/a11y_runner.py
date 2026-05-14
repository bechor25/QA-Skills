"""Accessibility executor — thin Playwright wrapper for `category="accessibility"`."""

from __future__ import annotations

from pathlib import Path

from .base import Executor, ExecutionResult
from .playwright_runner import PlaywrightRunner


class A11yRunner(Executor):
    framework = "playwright"
    category = "accessibility"

    def __init__(self) -> None:
        self._pw = PlaywrightRunner()

    def available(self, project_root: Path) -> bool:
        return self._pw.available(project_root)

    def run(
        self,
        project_root: Path,
        test_files: list[str],
        timeout: int,
        category: str | None = None,
    ) -> ExecutionResult:
        effective_category = category or self.category
        result = self._pw.run(project_root, test_files, timeout, category=effective_category)
        # Rebrand the category so the report rolls it up as accessibility.
        result.category = effective_category
        return result
