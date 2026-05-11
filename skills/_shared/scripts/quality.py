#!/usr/bin/env python3
"""CLI wrapper around qa_skills.quality.compute_quality_score.

Usage:
    python skills/_shared/scripts/quality.py --report-data report-data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.quality import compute_quality_score  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="quality")
    parser.add_argument("--report-data", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.report_data).read_text(encoding="utf-8"))
    score = compute_quality_score(
        data.get("coverage_by_category", {}),
        data.get("flaky_tests", []),
        data.get("gaps", []),
    )
    print(json.dumps({"quality_score": score}))
