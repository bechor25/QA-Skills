#!/usr/bin/env python3
"""CLI wrapper around qa_skills.budget.

Examples:
    # Estimate fit for a category:
    python skills/_shared/scripts/budget.py estimate --files 100 --timeout 600

    # Which batches still need dispatch?
    python skills/_shared/scripts/budget.py pending \\
        --logs-dir .qa-skills/logs/run_2026_05_11 \\
        --category api --batch-count 12

    # Persist completion after Task call:
    python skills/_shared/scripts/budget.py mark-completed \\
        --logs-dir .qa-skills/logs/run_... \\
        --category api --index 5 \\
        --paths '["tests/api/auth/test_login.py"]'

    # Context-warm summary for a later batch:
    python skills/_shared/scripts/budget.py prior-summary \\
        --logs-dir .qa-skills/logs/run_... --category api
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Delegate to the in-module CLI to keep argument handling in one place.
runpy.run_module("qa_skills.budget", run_name="__main__")
