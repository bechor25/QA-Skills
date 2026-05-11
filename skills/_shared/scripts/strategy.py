#!/usr/bin/env python3
"""CLI wrapper around qa_skills.strategy.

Usage (signal only):
    python skills/_shared/scripts/strategy.py --analysis a.json --category api

Usage (apply server matrix for ui/a11y at Phase 2.5):
    python skills/_shared/scripts/strategy.py --analysis a.json --category ui \
        --with-server-gate [--allow-start]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.server import build_server_plan, is_reachable  # noqa: E402
from qa_skills.strategy import decide_category, has_signal  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="strategy")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--with-server-gate", action="store_true")
    parser.add_argument("--allow-start", action="store_true")
    args = parser.parse_args()

    a = load_analysis(args.analysis)
    if args.with_server_gate:
        plan = build_server_plan(a, allow_start_explicit=args.allow_start)
        reachable = bool(plan.url) and is_reachable(plan.url)
        ok, reason = decide_category(args.category, a, plan, reachable)
    else:
        ok, reason = has_signal(args.category, a)
    print(json.dumps({"category": args.category, "should_run": ok, "reason": reason}))
