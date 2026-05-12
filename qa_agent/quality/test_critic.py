"""Test critic.

Composes assertion + selector validators into a per-file score and a
list of findings. The score is a coarse 0-10:
  10 — no findings
   7 — only warnings
   4 — one or more errors
   1 — file unreadable / parse-error finding
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..shared.logging import get_logger
from ..state import schemas
from .assertion_validator import validate_test_file
from .import_validator import validate_imports
from .selector_validator import validate_selectors

log = get_logger("qa_agent.quality.test_critic")

_CRITICAL_RULES = {"read-failed", "import-unresolved"}


def critique_files(
    project_root: Path,
    tests: schemas.GeneratedTests,
) -> schemas.Critique:
    """Critique every generated test file. Returns a Critique state model."""
    results: list[schemas.CritiqueResult] = []
    for entry in tests.entries:
        abs_path = project_root / entry.path
        findings: list[schemas.CritiqueFinding] = list(validate_test_file(abs_path))
        findings.extend(validate_imports(abs_path))
        if entry.framework == "playwright":
            findings.extend(validate_selectors(abs_path))
        score = _score(findings)
        results.append(
            schemas.CritiqueResult(
                test_path=entry.path,
                scenario_id=entry.scenario_id,
                score=score,
                findings=findings,
            )
        )
    log.info("critic: %d files reviewed", len(results))
    return schemas.Critique(built_at=datetime.now(timezone.utc), results=results)


def _score(findings: list[schemas.CritiqueFinding]) -> float:
    if not findings:
        return 10.0
    if any(f.rule == "read-failed" for f in findings):
        return 1.0
    if any(f.rule in _CRITICAL_RULES for f in findings):
        # File can't execute (broken import or read failure). Hard fail.
        return 2.0
    if any(f.severity == "error" for f in findings):
        return 4.0
    return 7.0
