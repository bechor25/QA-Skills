#!/usr/bin/env python3
"""CLI wrapper around qa_skills.git_diff.update_analysis.

Usage:
    python skills/_shared/scripts/git_diff.py --analysis a.json [--project-root /abs/path]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.git_diff import update_analysis  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="git_diff")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    summary = update_analysis(args.analysis, args.project_root)
    print(json.dumps({
        "agent": "qa-git-diff-analyzer",
        "status": "completed",
        "summary": summary,
    }))
