#!/usr/bin/env python3
"""CLI wrapper around qa_skills.report_builder.build_report_data.

Replaces the qa-coverage-reporter LLM JSON-assembly step. The orchestrator
calls this in Phase 6 with paths to all runtime artifacts; the wrapper reads
every `agent_output_*.json` from logs_dir (written by B4) and produces a v2
report-data.json.

Hard contract:
  * report-data.json MUST have `version: "2.0"`.
  * coverage_by_category[<cat>] MUST contain
    `{pct, covered_items[], missing_items[], total, files[], stub_files[], status}`.

Usage:
    python skills/_shared/scripts/build_report.py \
        --run-id "${RUN_ID}" \
        --project-root "${PROJECT_ROOT}" \
        --analysis "${LOGS_DIR}/analysis.json" \
        --logs-dir "${LOGS_DIR}" \
        --strategy "${LOGS_DIR}/strategy.json" \
        --flaky "${LOGS_DIR}/flaky.json" \
        --state  "${PROJECT_ROOT}/test-state.json" \
        --out    "${PROJECT_ROOT}/test-reports/report-data.json"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.report_builder import build_report_data  # noqa: E402


def _read_json(path: Path | None) -> dict | list | None:
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _collect_agent_outputs(logs_dir: Path) -> list[dict]:
    """Read every `agent_output_<agent>.json` (merged form, not per-batch).

    B4 emits both per-batch and merged files. The merged file is the canonical
    AgentResult-shaped record for one agent.
    """
    outputs: list[dict] = []
    for f in sorted(logs_dir.glob("agent_output_*.json")):
        if "_batch_" in f.name:
            continue  # skip per-batch; merged file already aggregates them
        data = _read_json(f)
        if isinstance(data, dict):
            outputs.append(data)
    return outputs


def _collect_execution_results(logs_dir: Path) -> dict[str, dict]:
    """Read every `execution_<agent>.json` written by sub-agents (run_tests wrapper).

    Returns {agent_name: canonical_runner_result}. Missing/corrupt files are
    silently skipped so report assembly never fails on telemetry gaps.
    """
    out: dict[str, dict] = {}
    for f in sorted(logs_dir.glob("execution_*.json")):
        agent = f.stem.removeprefix("execution_")
        data = _read_json(f)
        if isinstance(data, dict):
            out[agent] = data
    return out


def _collect_warnings(logs_dir: Path) -> list[str]:
    """Aggregate orchestrator-emitted warnings written under logs_dir."""
    warnings: list[str] = []
    w_path = logs_dir / "warnings.json"
    data = _read_json(w_path)
    if isinstance(data, list):
        warnings.extend(w for w in data if isinstance(w, str))
    # Also pick up per-agent warnings from the merged outputs.
    for f in sorted(logs_dir.glob("agent_output_*.json")):
        if "_batch_" in f.name:
            continue
        data = _read_json(f)
        if isinstance(data, dict):
            for w in data.get("warnings", []) or []:
                if isinstance(w, str):
                    warnings.append(w)
    return sorted(set(warnings))


def main() -> int:
    parser = argparse.ArgumentParser(prog="build_report")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--strategy", default=None)
    parser.add_argument("--flaky", default=None)
    parser.add_argument("--state", default=None)
    parser.add_argument("--locale", default="en")
    parser.add_argument("--run-type", default="full")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.is_dir():
        print(f"FAIL: logs_dir does not exist: {logs_dir}", file=sys.stderr)
        return 2

    analysis = load_analysis(args.analysis)
    all_test_outputs = _collect_agent_outputs(logs_dir)

    strategy = _read_json(Path(args.strategy)) if args.strategy else None
    flaky    = _read_json(Path(args.flaky))    if args.flaky    else None
    state    = _read_json(Path(args.state))    if args.state    else None

    flaky_tests: list[dict] = []
    if isinstance(flaky, dict):
        flaky_tests = flaky.get("flaky_tests") or []
    elif isinstance(flaky, list):
        flaky_tests = flaky

    env_categories_removed: list[dict] = []
    env_installs_performed: list[dict] = []
    timeline: list[dict] = []
    if isinstance(strategy, dict):
        env_categories_removed = strategy.get("env_categories_removed") or []
        env_installs_performed = strategy.get("env_installs_performed") or []
        timeline = strategy.get("timeline") or []

    warnings = _collect_warnings(logs_dir)
    execution_results = _collect_execution_results(logs_dir)

    report = build_report_data(
        run_id=args.run_id,
        project_root=args.project_root,
        analysis=analysis,
        all_test_outputs=all_test_outputs,
        env_categories_removed=env_categories_removed,
        env_installs_performed=env_installs_performed,
        state=state,
        flaky_tests=flaky_tests,
        run_type=args.run_type,
        timeline=timeline,
        locale=args.locale,
        warnings=warnings,
        execution_results=execution_results,
    )

    # Hard schema gate — refuse to write a malformed report.
    if report.get("version") != "2.0":
        print(f"FAIL: report version mismatch: {report.get('version')!r}", file=sys.stderr)
        return 3
    required_keys = {"pct", "covered_items", "missing_items", "total", "files", "stub_files", "status", "execution"}
    for cat, info in (report.get("coverage_by_category") or {}).items():
        if not isinstance(info, dict):
            continue
        missing_keys = required_keys - set(info.keys())
        if missing_keys:
            print(
                f"FAIL: coverage_by_category[{cat}] missing keys: {sorted(missing_keys)}",
                file=sys.stderr,
            )
            return 4

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    json.dump(
        {
            "status": "completed",
            "report_data_path": str(out_path),
            "version": report["version"],
            "quality_score": report["quality_score"],
            "agent_outputs_consumed": len(all_test_outputs),
            "execution_results_consumed": len(execution_results),
            "warnings_count": len(warnings),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
