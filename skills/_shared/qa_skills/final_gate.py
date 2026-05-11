"""Trimmed Phase 9 — only artifact existence + UI/a11y proof-of-run + learnings audit.

The legacy 9b/9c/9d.1.x/9d.3 checks are gone because the upstream contract makes
them impossible to fail (path_contract enforced at sub-agent input, coverage
math built from agent_outputs). This module ships only the cheap, real checks.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any


def _check_artifacts(project_root: Path, run_id: str) -> list[str]:
    """9a — the four contract artifacts must exist on disk."""
    expected = [
        project_root / "test-state.json",
        project_root / "test-reports" / "report-data.json",
        project_root / ".qa-skills" / "checkpoints" / "run.json",
    ]
    warnings: list[str] = []
    for p in expected:
        if not p.exists():
            warnings.append(f"missing_artifact:{p.relative_to(project_root)}")

    html_glob = list((project_root / "test-reports").glob("report-*.html"))
    if not html_glob:
        warnings.append("missing_artifact:test-reports/report-*.html")
    return warnings


def _check_ui_proof(report_data: dict, project_root: Path) -> list[str]:
    """9d.2 — UI/a11y must have ≥1 PNG screenshot when status is passed/partial."""
    warnings: list[str] = []
    cov = report_data.get("coverage_by_category", {})

    for category in ("ui", "a11y"):
        c = cov.get(category)
        if not c or c.get("status") not in ("passed", "partial", "completed"):
            continue
        artifacts = report_data.get(f"{category}_artifacts") or {}
        results_dir = artifacts.get("test_results_dir")
        if not results_dir or not Path(results_dir).is_dir():
            warnings.append(f"{category}_test_results_dir_missing")
            continue
        png_count = len(glob.glob(str(Path(results_dir) / "**" / "*.png"), recursive=True))
        if png_count == 0:
            warnings.append(f"{category}_no_screenshots_captured")
    return warnings


def _check_learnings_audit(report_data: dict, project_root: Path) -> list[str]:
    """9e — sanity-check the learnings audit log when active."""
    warnings: list[str] = []
    ls = report_data.get("learnings_summary") or {}
    activity = (
        ls.get("added_this_run", 0)
        + ls.get("incremented_this_run", 0)
        + ls.get("rejected_this_run", 0)
    )
    log_path = ls.get("log_path")
    if activity > 0 and (not log_path or not Path(log_path).exists()):
        warnings.append("learnings_log_missing_despite_activity")

    lj = project_root / ".qa-skills" / "learnings.json"
    if lj.exists():
        try:
            data = json.loads(lj.read_text(encoding="utf-8"))
            if data.get("version") != "1.0":
                warnings.append(f"learnings_json_unexpected_version:{data.get('version')}")
        except (OSError, json.JSONDecodeError) as e:
            warnings.append(f"learnings_json_corrupt:{type(e).__name__}")
    return warnings


def run_final_gate(report_data_path: str | Path, project_root: str | Path, run_id: str) -> dict[str, Any]:
    """Execute 9a + 9d.2 + 9e. Return {status, warnings}.

    status = "completed" only if zero warnings.
    """
    rd_path = Path(report_data_path)
    pr = Path(project_root)
    warnings: list[str] = []

    if not rd_path.exists():
        warnings.append(f"missing_artifact:{rd_path.relative_to(pr)}")
        return {"status": "partial", "warnings": warnings}

    try:
        report_data = json.loads(rd_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "partial", "warnings": [f"report_data_unreadable:{type(e).__name__}"]}

    warnings.extend(_check_artifacts(pr, run_id))
    warnings.extend(_check_ui_proof(report_data, pr))
    warnings.extend(_check_learnings_audit(report_data, pr))

    return {
        "status": "completed" if not warnings else "partial",
        "warnings": warnings,
    }


__all__ = ["run_final_gate"]


# CLI entry: python -m qa_skills.final_gate --report-data <path> --project-root <path> --run-id <id>
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.final_gate")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    result = run_final_gate(args.report_data, args.project_root, args.run_id)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    sys.exit(0 if result["status"] == "completed" else 1)
