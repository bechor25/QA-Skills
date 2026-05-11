#!/usr/bin/env python3
"""CLI wrapper around qa_skills.server.build_server_plan.

Usage:
    python skills/_shared/scripts/server_plan.py --analysis a.json [--mode auto|interactive] [--allow-start]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.server import build_server_plan  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="server_plan")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--mode", default="auto", choices=("auto", "interactive"))
    parser.add_argument("--allow-start", action="store_true",
                        help="Set start_allowed=True (user opted in to background-spawn the dev server).")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    analysis = load_analysis(args.analysis)
    plan = build_server_plan(
        analysis,
        mode=args.mode,
        allow_start_explicit=True if args.allow_start else None,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(dataclasses.asdict(plan), indent=2))
