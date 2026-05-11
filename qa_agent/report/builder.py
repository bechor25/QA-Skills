"""Pure-Python report data builder.

Reads every state file and emits a single JSON-serializable dict the
renderer consumes. There is intentionally no LLM step here: the data is
the data, and the quality score is computed deterministically from
state. The LLM cannot inflate the verdict.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ..quality.coverage_intelligence import compute_coverage
from ..state import schemas
from ..state.manager import StateManager


def build_report_data(project: str | None) -> dict[str, Any]:
    sm = StateManager(project)
    pm = sm.project_map()
    kg = sm.knowledge_graph()
    risk = sm.risk_matrix()
    strategy = sm.strategy()
    scenarios = sm.load(schemas.Scenarios)
    tests = sm.load(schemas.GeneratedTests)
    critique = sm.load(schemas.Critique)
    history = sm.execution_history()
    installs = sm.installation_history()
    flaky = sm.flaky_state()

    coverage = compute_coverage(risk, strategy, history)
    aggregate = _aggregate_execution(history)
    quality_score = _quality_score(aggregate, critique, flaky)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "root": pm.project_root,
            "summary": kg.project_summary,
            "languages": pm.languages,
            "frameworks": [f.model_dump() for f in pm.frameworks],
            "package_managers": pm.package_managers,
        },
        "executive_summary": {
            "quality_score": quality_score,
            "passed": aggregate["passed"],
            "failed": aggregate["failed"],
            "skipped": aggregate["skipped"],
            "tests_total": aggregate["total"],
            "pass_rate": aggregate["pass_rate"],
            "flaky": len(flaky.entries),
            "critique_avg": _avg(r.score for r in critique.results),
        },
        "risk": [
            {
                "capability": r.capability,
                "feature_id": r.feature_id,
                "score": r.score,
                "band": _band(r.score),
                "axes": {
                    "business_impact": r.business_impact,
                    "state_complexity": r.state_complexity,
                    "security_exposure": r.security_exposure,
                    "change_frequency": r.change_frequency,
                },
                "rationale": r.rationale,
            }
            for r in risk.entries
        ],
        "strategy": [s.model_dump() for s in strategy.entries],
        "coverage": coverage,
        "scenarios": _scenarios_overview(scenarios),
        "tests": _tests_overview(tests, history),
        "critique": _critique_overview(critique),
        "flaky": [f.model_dump() for f in flaky.entries],
        "installations": [i.model_dump() for i in installs.records[-50:]],
        "executions": [e.model_dump() for e in history.records[-200:]],
    }


# ---------------------------------------------------------------------------

def _aggregate_execution(history: schemas.ExecutionHistory) -> dict[str, Any]:
    passed = failed = skipped = 0
    if history.records:
        last_run = history.records[-1].run_id
        for rec in history.records:
            if rec.run_id != last_run:
                continue
            passed += rec.passed
            failed += rec.failed
            skipped += rec.skipped
    total = passed + failed + skipped
    pass_rate = round((passed / total) * 100, 1) if total else 0.0
    return {"passed": passed, "failed": failed, "skipped": skipped, "total": total, "pass_rate": pass_rate}


def _quality_score(
    aggregate: dict[str, Any],
    critique: schemas.Critique,
    flaky: schemas.FlakyState,
) -> int:
    if aggregate["total"] == 0:
        return 0
    pass_pts = aggregate["pass_rate"]   # already 0-100
    critic_avg = _avg(r.score for r in critique.results)
    critic_pts = (critic_avg / 10.0) * 100 if critic_avg else 0
    flaky_pen = min(20, len(flaky.entries) * 3)
    raw = 0.7 * pass_pts + 0.3 * critic_pts - flaky_pen
    return max(0, min(100, int(round(raw))))


def _band(score: float) -> str:
    if score >= 28.0:
        return "high"
    if score >= 18.0:
        return "medium"
    return "low"


def _scenarios_overview(s: schemas.Scenarios) -> dict[str, Any]:
    by_cat: Counter[str] = Counter()
    by_cap: Counter[str] = Counter()
    for sc in s.entries:
        by_cat[sc.category] += 1
        by_cap[sc.capability] += 1
    return {
        "count": len(s.entries),
        "by_category": dict(by_cat),
        "by_capability": dict(by_cap),
    }


def _tests_overview(tests: schemas.GeneratedTests, history: schemas.ExecutionHistory) -> dict[str, Any]:
    by_cat: Counter[str] = Counter()
    by_fw: Counter[str] = Counter()
    for t in tests.entries:
        by_cat[t.category] += 1
        by_fw[t.framework] += 1
    last_run_results: dict[str, dict[str, int]] = {}
    if history.records:
        last_run = history.records[-1].run_id
        for rec in history.records:
            if rec.run_id != last_run:
                continue
            bucket = last_run_results.setdefault(
                rec.category, {"passed": 0, "failed": 0, "skipped": 0}
            )
            bucket["passed"] += rec.passed
            bucket["failed"] += rec.failed
            bucket["skipped"] += rec.skipped
    return {
        "count": len(tests.entries),
        "by_category": dict(by_cat),
        "by_framework": dict(by_fw),
        "last_run_by_category": last_run_results,
    }


def _critique_overview(c: schemas.Critique) -> dict[str, Any]:
    rule_counts: Counter[str] = Counter()
    severities: Counter[str] = Counter()
    for r in c.results:
        for f in r.findings:
            rule_counts[f.rule] += 1
            severities[f.severity] += 1
    return {
        "files_reviewed": len(c.results),
        "avg_score": round(_avg(r.score for r in c.results), 2),
        "by_rule": dict(rule_counts),
        "by_severity": dict(severities),
    }


def _avg(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0
