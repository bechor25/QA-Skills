#!/usr/bin/env python3
"""CLI wrapper around qa_skills.runner.run_tests.

Used by sub-agent Phase 8 (Track C3.b) to execute the tests the agent just
emitted and produce a canonical structured execution_result the orchestrator
trusts. Exit code matches runner exit code (0 = clean pass).

Usage:
    python skills/_shared/scripts/run_tests.py \
        --category api --project-root /abs/path --language typescript \
        --files-json .qa-skills/logs/<run>/agent_output_qa-api-test.json \
        --out       .qa-skills/logs/<run>/execution_qa-api-test.json
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

runpy.run_module("qa_skills.runner", run_name="__main__")
