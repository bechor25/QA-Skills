#!/usr/bin/env python3
"""CLI wrapper around qa_skills.final_gate.

Usage:
    python skills/_shared/scripts/final_gate.py --report-data .../report-data.json \
        --project-root /abs/proj --run-id <uuid>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.final_gate import run_final_gate  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="final_gate")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    result = run_final_gate(args.report_data, args.project_root, args.run_id)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "completed" else 1)
