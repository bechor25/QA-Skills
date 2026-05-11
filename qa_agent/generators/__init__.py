"""Test generators per category.

Each generator turns a `Scenario` into a concrete test file written to
the target project under `tests/qa-agent/<category>/`. Generators are
template-driven by default; the LLM may replace bodies via the
generation loop in `cli/commands/full_run.py` (Phase 3.11).
"""

from .base import GeneratedFile, slugify  # noqa: F401
