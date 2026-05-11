#!/usr/bin/env python3
"""CLI wrapper around qa_skills.flaky.detect_flaky.

Usage:
    python skills/_shared/scripts/flaky.py \
      --project-root /abs/path \
      --language python \
      [--runs 3] [--locale en]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.flaky import detect_flaky  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="flaky")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--language", required=True, choices=("typescript", "javascript", "python"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--locale", default="en", choices=("he", "en"))
    args = parser.parse_args()

    result = detect_flaky(args.project_root, args.language, runs=args.runs, locale=args.locale)
    print(json.dumps(result, indent=2))
