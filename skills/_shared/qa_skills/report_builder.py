"""Build report-data.json from analysis + agent_outputs + flaky + state + timeline.

Replaces the bulk of qa-coverage-reporter.md Phase 5. Pure deterministic
assembly. The agent.md still owns the Task call into qa-html-reporter; this
module handles the data construction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import Analysis
from .coverage import compute_coverage
from .artifacts import collect_artifacts
from .gaps import identify_gaps
from .quality import compute_quality_score

REPORT_DATA_VERSION = "2.0"

CATEGORY_TO_AGENT = {
    "unit":     "qa-unit-test",
    "api":      "qa-api-test",
    "ui":       "qa-ui-test",
    "security": "qa-security-test",
    "a11y":     "qa-a11y-test",
    "contract": "qa-contract-test",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _agent_output(all_test_outputs: list[dict], agent_name: str) -> dict | None:
    return next((o for o in all_test_outputs if o.get("agent") == agent_name), None)


def _normalize_status(s: str | None) -> str:
    if not s:
        return "skipped:not_generated"
    if s in ("passed", "partial", "error", "completed"):
        return "passed" if s == "completed" else s
    if s.startswith("skipped:"):
        return s
    if s.startswith("skipped_"):
        # Translate legacy snake_case → closed enum
        return "skipped:" + s[len("skipped_"):]
    if s == "not_generated":
        return "skipped:not_generated"
    return "error"


def _empty_execution() -> dict[str, Any]:
    """Shape-stable execution block when no execution_result is available."""
    return {
        "runner": None,
        "total": 0, "passed": 0, "failed": 0, "skipped": 0,
        "duration_ms": 0, "failures": [], "exit_code": None,
    }


def _empty_coverage(status: str, **extra: Any) -> dict[str, Any]:
    """Shape-stable v2 coverage entry for skipped/error/not_generated categories."""
    base: dict[str, Any] = {
        "pct": 0,
        "covered_items": [],
        "missing_items": [],
        "total": 0,
        "files": [],
        "stub_files": [],
        "status": status,
        "execution": _empty_execution(),
    }
    base.update(extra)
    return base


def _execution_for_agent(
    execution_results: dict[str, dict] | None, agent: str
) -> dict[str, Any]:
    """Return execution block keyed by agent name; empty when absent."""
    if not execution_results:
        return _empty_execution()
    info = execution_results.get(agent)
    if not isinstance(info, dict):
        return _empty_execution()
    return {
        "runner":      info.get("runner"),
        "total":       int(info.get("total") or 0),
        "passed":      int(info.get("passed") or 0),
        "failed":      int(info.get("failed") or 0),
        "skipped":     int(info.get("skipped") or 0),
        "duration_ms": int(info.get("duration_ms") or 0),
        "failures":    list(info.get("failures") or []),
        "exit_code":   info.get("exit_code"),
        "note":        info.get("note"),
    }


def build_coverage_by_category(
    analysis: Analysis,
    all_test_outputs: list[dict],
    env_categories_removed: list[dict],
    project_root: str | Path,
    execution_results: dict[str, dict] | None = None,
) -> dict[str, dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    for cat, agent in CATEGORY_TO_AGENT.items():
        # 1. env-validator removed?
        removed = next((r for r in env_categories_removed if r.get("name") == cat), None)
        if removed:
            coverage[cat] = _empty_coverage(
                "skipped:env_removed",
                reason=removed.get("reason"),
                action=removed.get("action"),
            )
            continue

        agent_out = _agent_output(all_test_outputs, agent)
        if agent_out is None:
            coverage[cat] = _empty_coverage("skipped:not_generated")
            continue

        normalized = _normalize_status(agent_out.get("status"))
        if normalized.startswith("skipped:") or normalized == "error":
            coverage[cat] = _empty_coverage(
                normalized, reason=agent_out.get("reason")
            )
            continue

        cov = compute_coverage(
            cat, agent_out.get("outputs", []), analysis, project_root=project_root
        )
        cov["status"] = normalized
        # If the sub-agent returned missing_items from A2, merge them so the
        # report shows the honest gap even when no coverage call surfaced them.
        agent_missing = agent_out.get("missing_items") or []
        if agent_missing:
            cov["missing_items"] = sorted(
                set(cov.get("missing_items", []) or []) | set(agent_missing)
            )

        # C3.c: attach execution block. Prefer the agent's embedded
        # execution_result; fall back to the per-agent execution_*.json file
        # captured from logs_dir by the wrapper.
        embedded = agent_out.get("execution_result")
        if isinstance(embedded, dict):
            cov["execution"] = _execution_for_agent({agent: embedded}, agent)
        else:
            cov["execution"] = _execution_for_agent(execution_results, agent)

        # Downgrade status when execution shows failures the agent did not flag.
        if cov["execution"]["failed"] > 0 and cov["status"] == "passed":
            cov["status"] = "partial"
        if cov["execution"]["exit_code"] == 127 and cov["status"] == "passed":
            cov["status"] = "skipped:runner_missing"

        coverage[cat] = cov

        # ui/a11y get artifacts inline too
        if cat in ("ui", "a11y"):
            art = collect_artifacts(agent_out, cat, project_root)
            if art:
                coverage[cat]["artifacts"] = art

    return coverage


def _covered_modules(coverage: dict[str, dict]) -> set[str]:
    return set(coverage.get("unit", {}).get("covered_items", []) or [])


def _covered_routes(coverage: dict[str, dict]) -> set[str]:
    return set(coverage.get("api", {}).get("covered_items", []) or [])


def _secured_modules(coverage: dict[str, dict], analysis: Analysis) -> set[str]:
    """Map covered_items in security category back to source modules.

    `coverage[security].covered_items` are 'METHOD /path' route ids — map via routes[i].file.
    """
    covered = set(coverage.get("security", {}).get("covered_items", []) or [])
    files: set[str] = set()
    for r in analysis.routes:
        if r.covers_id in covered:
            files.add(r.file)
    return files


def build_report_data(
    *,
    run_id: str,
    project_root: str | Path,
    analysis: Analysis,
    all_test_outputs: list[dict],
    env_categories_removed: list[dict],
    env_installs_performed: list[dict] | None = None,
    state: dict | None = None,
    flaky_tests: list[dict] | None = None,
    run_type: str = "full",
    timeline: list[dict] | None = None,
    locale: str = "en",
    warnings: list[str] | None = None,
    learnings_summary: dict | None = None,
    execution_results: dict[str, dict] | None = None,
) -> dict:
    """Assemble the full report-data dict.

    `execution_results` is an agent-name -> canonical-runner-result map (the
    shape emitted by `qa_skills.runner.run_tests`). When supplied, every
    `coverage_by_category[cat].execution` block is populated from it; agents
    that embedded `execution_result` in their AgentResult take precedence.

    Returns the dict; does NOT write to disk. Caller (qa-coverage-reporter agent)
    writes it after final tweaks.
    """
    flaky_tests = flaky_tests or []
    timeline = timeline or []
    warnings = list(warnings or [])

    coverage = build_coverage_by_category(
        analysis, all_test_outputs, env_categories_removed, project_root,
        execution_results=execution_results,
    )

    gaps = identify_gaps(
        modules=analysis.modules,
        routes=analysis.routes,
        covered_modules=_covered_modules(coverage),
        covered_routes=_covered_routes(coverage),
        secured_modules=_secured_modules(coverage, analysis),
    )

    quality_score = compute_quality_score(coverage, flaky_tests, gaps)

    # Promote ui/a11y artifacts to top-level for html-reporter
    ui_art = coverage.get("ui", {}).get("artifacts") or {
        "playwright_report": None, "test_results_dir": None,
        "screenshots": [], "videos": [], "traces": [],
    }
    a11y_art = coverage.get("a11y", {}).get("artifacts") or {
        "axe_report": None, "test_results_dir": None, "screenshots": [],
    }

    # Collapse vulnerabilities_found across all agent outputs
    vulns: list[dict] = []
    for o in all_test_outputs or []:
        for spec in o.get("outputs", []) or []:
            for v in spec.get("vulnerabilities_found", []) or []:
                vulns.append(v)

    # Counts
    tests_new = sum(
        sum(spec.get("tests_written", 0) for spec in (o.get("outputs", []) or []))
        for o in (all_test_outputs or [])
    )

    return {
        "version": REPORT_DATA_VERSION,
        "run_id": run_id,
        "project_root": str(project_root),
        "language": analysis.language,
        "locale": locale,
        "generated_at": _now_iso(),
        "run_type": run_type,
        "quality_score": quality_score,
        "summary": {
            "modules_total": len(analysis.modules),
            "tests_new": tests_new,
            "tests_updated": 0,
            "tests_unchanged": 0,
            "flaky_count": len(flaky_tests),
        },
        "coverage_by_category": coverage,
        "modules": [
            {"path": m.path, "type": m.type, "diff_class": m.diff_class}
            for m in analysis.modules
        ],
        "vulnerabilities_found": vulns,
        "gaps": gaps,
        "blind_spots": [],
        "recommendations": [],
        "flaky_tests": flaky_tests,
        "timeline": timeline,
        "warnings": warnings,
        "ui_artifacts": ui_art,
        "a11y_artifacts": a11y_art,
        "env_installs_performed": env_installs_performed or [],
        "env_categories_removed": env_categories_removed or [],
        "learnings_summary": learnings_summary or {
            "added_this_run": 0, "incremented_this_run": 0,
            "rejected_this_run": 0, "promoted_this_run": 0, "log_path": None,
        },
    }


__all__ = ["build_report_data", "build_coverage_by_category", "REPORT_DATA_VERSION", "CATEGORY_TO_AGENT"]


# CLI wrapper: skills/_shared/scripts/report_builder.py
if __name__ == "__main__":
    import argparse
    import sys

    from .analysis import load_analysis

    parser = argparse.ArgumentParser(prog="qa_skills.report_builder")
    parser.add_argument("--inputs", required=True, help="Path to JSON with all builder inputs")
    parser.add_argument("--out", required=True, help="Where to write report-data.json")
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
    sys.exit(0)
