#!/usr/bin/env python3
"""CLI wrapper around qa_skills.agent_log.

Examples:
    # After each Task call in Phase 3:
    echo "$AGENT_RESULT_JSON" | python skills/_shared/scripts/agent_log.py write \\
        --logs-dir .qa-skills/logs/run_2026_05_11 \\
        --agent qa-api-test --batch-index 0

    # End of category dispatch — merge per-batch logs:
    python skills/_shared/scripts/agent_log.py merge \\
        --logs-dir .qa-skills/logs/run_2026_05_11 \\
        --agent qa-api-test
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

runpy.run_module("qa_skills.agent_log", run_name="__main__")
