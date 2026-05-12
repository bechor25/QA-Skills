"""Coverage intelligence.

Feature-level coverage (not line coverage):

  - per capability: which categories of tests were planned vs. executed
  - per feature: number of routes/pages covered by at least one test
  - per risk band: % of high/medium/low-risk features with passing tests

Output is a JSON-friendly dict that the report renderer consumes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..state import schemas


def compute_coverage(
    risk: schemas.RiskMatrix,
    strategy: schemas.Strategy,
    history: schemas.ExecutionHistory,
) -> dict[str, Any]:
    """Return a coverage summary dictionary."""
    planned_per_feature: dict[str, set[str]] = defaultdict(set)
    for s in strategy.entries:
        if s.feature_id:
            planned_per_feature[s.feature_id].update(s.categories)

    executed_per_feature: dict[str, set[str]] = defaultdict(set)
    pass_per_feature: dict[str, int] = defaultdict(int)
    fail_per_feature: dict[str, int] = defaultdict(int)
    for rec in history.records:
        # category-level rollup — feature association lives in the test
        # file naming convention `<feature_id>__<category>.spec`; until
        # generators are wired, we just attribute by category.
        for fid in planned_per_feature:
            if rec.category in planned_per_feature[fid]:
                executed_per_feature[fid].add(rec.category)
                pass_per_feature[fid] += rec.passed
                fail_per_feature[fid] += rec.failed

    by_feature: list[dict[str, Any]] = []
    total_passed = 0
    total_attempted = 0
    for fid, planned in planned_per_feature.items():
        executed = executed_per_feature.get(fid, set())
        passed = pass_per_feature.get(fid, 0)
        failed = fail_per_feature.get(fid, 0)
        attempted = passed + failed
        total_passed += passed
        total_attempted += attempted
        eff = (passed / attempted) if attempted else 0.0
        by_feature.append(
            {
                "feature_id": fid,
                "planned_categories": sorted(planned),
                "executed_categories": sorted(executed),
                "planned_count": len(planned),
                "executed_count": len(executed),
                "tests_passed": passed,
                "tests_failed": failed,
                # Categories planned vs executed — does *not* reflect
                # whether the executed tests passed.
                "coverage_ratio": (len(executed) / len(planned)) if planned else 0.0,
                # Tests that actually passed out of attempted — the
                # honest measure for stakeholders.
                "effective_coverage": eff,
            }
        )

    risk_buckets: dict[str, dict[str, int]] = {
        "high":   {"total": 0, "covered": 0},
        "medium": {"total": 0, "covered": 0},
        "low":    {"total": 0, "covered": 0},
    }
    for r in risk.entries:
        band = _risk_band(r.score)
        risk_buckets[band]["total"] += 1
        if r.feature_id and executed_per_feature.get(r.feature_id):
            risk_buckets[band]["covered"] += 1

    return {
        "by_feature": by_feature,
        "by_risk": risk_buckets,
        "total_planned_features": len(planned_per_feature),
        "total_executed_features": sum(1 for v in executed_per_feature.values() if v),
        "effective_coverage": (total_passed / total_attempted) if total_attempted else 0.0,
    }


def _risk_band(score: float) -> str:
    if score >= 28.0:
        return "high"
    if score >= 18.0:
        return "medium"
    return "low"
