#!/usr/bin/env python3
"""CLI wrapper around qa_skills.learnings.validate_learnings.

Usage:
    python skills/_shared/scripts/learnings.py --project-root /abs/path [--run-id <id>] [--now <iso>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.learnings import validate_learnings  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="learnings")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--now", default=None)
    args = parser.parse_args()

    result = validate_learnings(args.project_root, run_id=args.run_id, now=args.now)
    print(json.dumps(result, indent=2))
