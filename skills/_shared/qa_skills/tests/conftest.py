"""Make `qa_skills` importable when pytest runs from any cwd."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent.parent  # skills/_shared/
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# Also expose `scripts/` so tests can `import qa_run` directly.
_SCRIPTS = _SHARED / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture(autouse=True)
def _disable_real_flaky_runner(monkeypatch):
    """Prevent qa_run's Phase 5 from spawning real `pytest`/`vitest` × 3
    runs during the test suite. Tests that need to exercise flaky behavior
    override `qa_run.detect_flaky` explicitly inside the test.

    `try/except ImportError` keeps this benign when `qa_run` isn't loaded
    (e.g. when running only the qa_skills/* unit tests in isolation).
    """
    try:
        import qa_run  # noqa: F401
    except ImportError:
        return
    monkeypatch.setattr(
        "qa_run.detect_flaky",
        lambda **kw: {"flaky_tests": [], "runs_completed": 0,
                      "skipped": "disabled_in_tests"},
        raising=False,
    )
