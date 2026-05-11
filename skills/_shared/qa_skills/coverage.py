"""Real-units coverage math.

Replaces the legacy `passed_files / total_routes` formula. Coverage is computed
over actual covered items (route IDs / module paths / page paths) collected from
agent outputs, intersected with the universe derived from the analysis.

B2: stub-aware mode. When `project_root` is supplied, every agent_output is
read from disk and dropped from the covered set if its body matches a stub
marker. This prevents fake-green coverage when a sub-agent emitted a
placeholder file. Stub-marked files also surface as `stub_files[]` in the
result so the report layer can banner them (B3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

from .stub_markers import is_stub
from .types import Analysis


def _universe(category: str, analysis: Analysis) -> set[str]:
    if category == "unit":
        return {m.path for m in analysis.non_frontend_modules()}
    if category in ("api", "contract", "security"):
        return {r.covers_id for r in analysis.api_routes()}
    if category in ("ui", "a11y"):
        return {f.path for f in analysis.page_files()}
    return set()


def _output_is_stub(out: dict, project_root: Optional[Path]) -> bool:
    """True iff `project_root` is given and the file body matches a stub marker."""
    if project_root is None:
        return False
    path = out.get("path") if isinstance(out, dict) else None
    if not isinstance(path, str) or not path:
        return False
    full = project_root / path
    if not full.is_file():
        return False
    try:
        return is_stub(full.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return False


def _covered_from_outputs(
    agent_outputs: Iterable[dict],
    project_root: Optional[Path] = None,
) -> tuple[set[str], list[str]]:
    """Return (covered_items, stub_files).

    When project_root is supplied (B2 stub-aware mode), an output whose file
    body matches `STUB_MARKERS` is *excluded* from `covered_items` and its
    path is reported in `stub_files`. Legacy path (project_root=None) keeps
    the old behaviour for callers that did not migrate.
    """
    covered: set[str] = set()
    stub_files: list[str] = []
    for out in agent_outputs or []:
        if not isinstance(out, dict):
            continue
        if _output_is_stub(out, project_root):
            p = out.get("path")
            if isinstance(p, str) and p:
                stub_files.append(p)
            continue  # do NOT count this output's covers — it is a placeholder

        # Per `path-contract.md`, outputs[].covers MUST mirror the expected_files entry's covers.
        for c in out.get("covers", []) or []:
            if isinstance(c, str) and c:
                covered.add(c)
        # Backwards-compatible fallback: assertions_covered may carry the same values.
        for c in out.get("assertions_covered", []) or []:
            if isinstance(c, str) and c:
                covered.add(c)
    return covered, sorted(set(stub_files))


def compute_coverage(
    category: str,
    agent_outputs: Iterable[dict],
    analysis: Analysis,
    project_root: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Compute pct/covered_items/missing_items/total/files for a single category.

    `agent_outputs` is the `outputs` list returned by the corresponding sub-agent.

    When `project_root` is supplied, coverage becomes stub-aware: an emitted
    test file whose body matches `STUB_MARKERS` is excluded from
    `covered_items` and added to `stub_files` so the report can banner it.
    """
    universe = _universe(category, analysis)
    root = Path(project_root) if project_root is not None else None
    covered, stub_files = _covered_from_outputs(agent_outputs, root)
    intersect = covered & universe
    pct = int(100 * len(intersect) / len(universe)) if universe else 0
    return {
        "pct": pct,
        "covered_items": sorted(intersect),
        "missing_items": sorted(universe - covered),
        "total": len(universe),
        "files": [
            out["path"] for out in (agent_outputs or [])
            if isinstance(out, dict) and out.get("path")
        ],
        "stub_files": stub_files,
    }


__all__ = ["compute_coverage"]
