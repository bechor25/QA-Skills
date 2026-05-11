"""Risk engine.

Reads the knowledge graph + project map + (optionally) git history,
produces a risk matrix per capability/feature. Score is a weighted blend
of:

  business_impact:   intrinsic to capability type (auth, payments, ...)
  state_complexity:  proportional to routes + modules touched
  security_exposure: intrinsic to capability type, modulated by exposure
  change_frequency:  bucketed from git log (last 180 days)

The scoring is intentionally deterministic — strategy can use it as the
ground truth and the LLM can reason *around* it, never overruling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..shared.git import file_change_frequency
from ..shared.logging import get_logger
from ..state import schemas

log = get_logger("qa_agent.quality.risk_engine")


# Per-capability intrinsic ratings (0-5 each).
_CAPABILITY_RATINGS: dict[str, dict[str, int]] = {
    "auth":        {"business_impact": 5, "security_exposure": 5},
    "payments":    {"business_impact": 5, "security_exposure": 5},
    "permissions": {"business_impact": 4, "security_exposure": 4},
    "user-mgmt":   {"business_impact": 4, "security_exposure": 3},
    "data-export": {"business_impact": 3, "security_exposure": 3},
    "file-upload": {"business_impact": 3, "security_exposure": 4},
    "search":      {"business_impact": 2, "security_exposure": 1},
    "admin":       {"business_impact": 4, "security_exposure": 4},
    "api-public":  {"business_impact": 3, "security_exposure": 3},
    "other":       {"business_impact": 1, "security_exposure": 1},
}

# Final score weights — multiply each axis by its weight, sum, round to 1dp.
_WEIGHTS = {
    "business_impact":   2.5,
    "state_complexity":  1.5,
    "security_exposure": 2.5,
    "change_frequency":  1.0,
}


def build_risk_matrix(
    project: str | Path | None,
    kg: schemas.KnowledgeGraph,
) -> schemas.RiskMatrix:
    """Produce a RiskMatrix from the KG; consults git for change frequency."""
    entries: list[schemas.RiskEntry] = []

    # Per-feature change-frequency aggregation — every feature has a set of
    # module paths in its symbols; collect them once, query git in batch.
    paths_per_feature: dict[str, list[str]] = {}
    for f in kg.features:
        paths = {s.path for s in f.symbols if s.path}
        paths_per_feature[f.id] = sorted(paths)

    all_paths = sorted({p for paths in paths_per_feature.values() for p in paths})
    freq = (
        file_change_frequency(Path(_project_root_from_kg(kg)), all_paths)
        if all_paths
        else {}
    )

    for feature in kg.features:
        cap = feature.capabilities[0] if feature.capabilities else "other"
        intrinsic = _CAPABILITY_RATINGS.get(cap, _CAPABILITY_RATINGS["other"])

        # state complexity: routes/pages cluster size, clamped 0-5
        sym_count = len(feature.symbols)
        state_complexity = min(5, max(1, sym_count // 2 + 1)) if sym_count else 0

        # change frequency: bucket max commit count across feature paths
        max_commits = max(
            (freq.get(p, 0) for p in paths_per_feature.get(feature.id, [])),
            default=0,
        )
        change_frequency = _bucket_change_freq(max_commits)

        score = round(
            _WEIGHTS["business_impact"] * intrinsic["business_impact"]
            + _WEIGHTS["state_complexity"] * state_complexity
            + _WEIGHTS["security_exposure"] * intrinsic["security_exposure"]
            + _WEIGHTS["change_frequency"] * change_frequency,
            1,
        )

        rationale = (
            f"{cap}: intrinsic impact={intrinsic['business_impact']}, "
            f"security={intrinsic['security_exposure']}; "
            f"state_complexity={state_complexity} from {sym_count} routes/pages; "
            f"change_frequency={change_frequency} (max {max_commits} commits / 180d)."
        )

        entries.append(
            schemas.RiskEntry(
                capability=cap,
                feature_id=feature.id,
                business_impact=intrinsic["business_impact"],
                state_complexity=state_complexity,
                security_exposure=intrinsic["security_exposure"],
                change_frequency=change_frequency,
                score=score,
                rationale=rationale,
            )
        )

    entries.sort(key=lambda e: e.score, reverse=True)
    log.info("risk: %d entries, top score=%s", len(entries), entries[0].score if entries else None)
    return schemas.RiskMatrix(built_at=datetime.now(timezone.utc), entries=entries)


def _project_root_from_kg(kg: schemas.KnowledgeGraph) -> str:
    # kg doesn't carry the project root directly; fall back to cwd.
    # The caller normally invokes risk after analyze, which set the cwd
    # context already.
    return "."


def _bucket_change_freq(commits: int) -> int:
    if commits <= 0:
        return 0
    if commits < 3:
        return 1
    if commits < 8:
        return 2
    if commits < 20:
        return 3
    if commits < 50:
        return 4
    return 5
