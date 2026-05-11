"""Quality score (0-100) from coverage + flaky + gaps.

Replaces the inline `compute_quality_score` block in qa-orchestrator.md Phase 7.
Pure function — no IO. Tested by `test_quality.py`.
"""

from __future__ import annotations

from typing import Any

WEIGHTS = {"unit": 0.3, "api": 0.3, "ui": 0.2, "security": 0.2}
MAX_SCORE = 100
MIN_SCORE = 0


def compute_quality_score(
    coverage_by_category: dict[str, dict[str, Any]],
    flaky_tests: list[dict] | None = None,
    gaps: list[dict] | None = None,
) -> int:
    """Score in [0, 100]. See qa-orchestrator.md Phase 7 for the formula."""
    flaky_tests = flaky_tests or []
    gaps = gaps or []

    score = 0.0
    for cat, weight in WEIGHTS.items():
        pct = coverage_by_category.get(cat, {}).get("pct", 0)
        score += pct * weight * 0.8

    score -= len(flaky_tests) * 2
    score -= sum(1 for g in gaps if g.get("severity") == "high") * 5

    if coverage_by_category.get("contract", {}).get("pct", 0) == 100:
        score += 5

    if coverage_by_category.get("a11y", {}).get("critical_violations", 1) == 0:
        score += 3

    return int(max(MIN_SCORE, min(MAX_SCORE, score)))


__all__ = ["compute_quality_score", "WEIGHTS", "MAX_SCORE", "MIN_SCORE"]


# CLI: python -m qa_skills.quality --report-data <path>
if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.quality")
    parser.add_argument("--report-data", required=True)
    args = parser.parse_args()

    data = json.loads(open(args.report_data, encoding="utf-8").read())
    score = compute_quality_score(
        data.get("coverage_by_category", {}),
        data.get("flaky_tests", []),
        data.get("gaps", []),
    )
    print(json.dumps({"quality_score": score}))
    sys.exit(0)
