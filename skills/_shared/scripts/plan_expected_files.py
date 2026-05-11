#!/usr/bin/env python3
"""CLI wrapper around qa_skills.path_planner.

Usage:
    python skills/_shared/scripts/plan_expected_files.py --analysis a.json --category api
    python skills/_shared/scripts/plan_expected_files.py --analysis a.json --all --out expected_files.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.path_planner import compute_expected_files  # noqa: E402

CATEGORIES = ("unit", "api", "ui", "security", "a11y", "contract")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="plan_expected_files")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--all", action="store_true", help="Plan all categories at once")
    parser.add_argument("--out", help="Write JSON to this path instead of stdout")
    args = parser.parse_args()

    if not args.all and not args.category:
        parser.error("either --category or --all required")

    a = load_analysis(args.analysis)
    if args.all:
        result = {
            cat: [ef.to_dict() for ef in compute_expected_files(cat, a, a.language)]
            for cat in CATEGORIES
        }
    else:
        result = [ef.to_dict() for ef in compute_expected_files(args.category, a, a.language)]

    payload = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
