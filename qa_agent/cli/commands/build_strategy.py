"""`qa-agent build-strategy` — rebuild strategy.json from the refined
capability map.

The orchestrator calls this after the qa-capability-mapper sub-agent
has refined `raw_capability_map.json` into `capability_map.json`. The
deterministic strategy is rebuilt with one entry per discovered
capability (each carrying concrete route/UI globs that the qa-enricher
will use as scope).

Falls back to the legacy risk-matrix-driven strategy when no
`capability_map.json` is present — useful for projects too small to
warrant clustering.
"""

from __future__ import annotations

import argparse

from ...quality.strategy_builder import build_baseline_strategy
from ...shared.logging import get_logger
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.build_strategy")


def run(args: argparse.Namespace) -> int:
    project = args.project
    sm = StateManager(project)

    risk = sm.risk_matrix()
    if not risk.entries:
        log.error("build-strategy: risk_matrix.json is empty — run `prepare` first")
        return 1

    cap_map = sm.load(schemas.CapabilityMap)
    if cap_map.capabilities:
        log.info("build-strategy: using refined capability_map (%d capabilities)",
                 len(cap_map.capabilities))
        strategy = build_baseline_strategy(risk, capability_map=cap_map)
    else:
        raw = sm.load(schemas.RawCapabilityMap)
        if raw.capabilities:
            log.info("build-strategy: capability_map empty, falling back to raw "
                     "clusterer output (%d capabilities)", len(raw.capabilities))
            # Promote raw to map shape so strategy_builder can consume it.
            promoted = schemas.CapabilityMap(
                built_at=raw.built_at,
                source="clusterer",
                capabilities=raw.capabilities,
            )
            strategy = build_baseline_strategy(risk, capability_map=promoted)
        else:
            log.info("build-strategy: no capability map at all, using legacy risk-driven flow")
            strategy = build_baseline_strategy(risk)

    sm.save(strategy)
    log.info("build-strategy: saved %d strategy entries", len(strategy.entries))
    return 0
