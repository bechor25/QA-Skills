"""Real-units coverage math.

Replaces the legacy `passed_files / total_routes` formula. Coverage is computed
over actual covered items (route IDs / module paths / page paths) collected from
agent outputs, intersected with the universe derived from the analysis.
"""

from __future__ import annotations

from typing import Any, Iterable

from .types import Analysis


def _universe(category: str, analysis: Analysis) -> set[str]:
    if category == "unit":
        return {m.path for m in analysis.non_frontend_modules()}
    if category in ("api", "contract", "security"):
        return {r.covers_id for r in analysis.api_routes()}
    if category in ("ui", "a11y"):
        return {f.path for f in analysis.page_files()}
    return set()


def _covered_from_outputs(agent_outputs: Iterable[dict]) -> set[str]:
    covered: set[str] = set()
    for out in agent_outputs or []:
        # Per `path-contract.md`, outputs[].covers MUST mirror the expected_files entry's covers.
        for c in out.get("covers", []) or []:
            if isinstance(c, str) and c:
                covered.add(c)
        # Backwards-compatible fallback: assertions_covered may carry the same values.
        for c in out.get("assertions_covered", []) or []:
            if isinstance(c, str) and c:
                covered.add(c)
    return covered


def compute_coverage(category: str, agent_outputs: Iterable[dict], analysis: Analysis) -> dict[str, Any]:
    """Compute pct/covered_items/missing_items/total/files for a single category.

    `agent_outputs` is the `outputs` list returned by the corresponding sub-agent.
    """
    universe = _universe(category, analysis)
    covered = _covered_from_outputs(agent_outputs)
    intersect = covered & universe
    pct = int(100 * len(intersect) / len(universe)) if universe else 0
    return {
        "pct": pct,
        "covered_items": sorted(intersect),
        "missing_items": sorted(universe - covered),
        "total": len(universe),
        "files": [out["path"] for out in (agent_outputs or []) if out.get("path")],
    }


__all__ = ["compute_coverage"]
