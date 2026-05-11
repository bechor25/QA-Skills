#!/usr/bin/env python3
"""CLI wrapper around qa_skills.strategy.has_signal.

Usage:
    python skills/_shared/scripts/strategy.py --analysis a.json --category api
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.strategy import has_signal  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="strategy")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--category", required=True)
    args = parser.parse_args()

    a = load_analysis(args.analysis)
    ok, reason = has_signal(args.category, a)
    print(json.dumps({"category": args.category, "should_run": ok, "reason": reason}))
