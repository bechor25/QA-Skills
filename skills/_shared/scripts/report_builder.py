#!/usr/bin/env python3
"""CLI wrapper around qa_skills.report_builder.build_report_data.

Usage:
    python skills/_shared/scripts/report_builder.py \
      --inputs inputs.json \
      --out report-data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.report_builder import build_report_data  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="report_builder")
    parser.add_argument("--inputs", required=True, help="Path to JSON with all builder inputs")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    analysis = load_analysis(inputs["analysis_path"])
    report = build_report_data(
        run_id=inputs["run_id"],
        project_root=inputs["project_root"],
        analysis=analysis,
        all_test_outputs=inputs.get("all_test_outputs", []),
        env_categories_removed=inputs.get("env_categories_removed", []),
        env_installs_performed=inputs.get("env_installs_performed", []),
        state=inputs.get("state"),
        flaky_tests=inputs.get("flaky_tests", []),
        run_type=inputs.get("run_type", "full"),
        timeline=inputs.get("timeline", []),
        locale=inputs.get("locale", "en"),
        warnings=inputs.get("warnings", []),
        learnings_summary=inputs.get("learnings_summary"),
    )
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "report_data_path": args.out,
        "quality_score": report["quality_score"],
    }))
