"""`qa-agent full-run` — end-to-end pipeline.

Phase 0/1/2/3 implementation:
  1. analyze (scan -> tech -> deps -> api -> ui -> KG -> risk -> strategy)
  2. scenarios baseline
  3. test generation + critique
Execution and reporting are wired in later phases.
"""

from __future__ import annotations

import argparse

from ...quality.generation_loop import run_generation_loop
from ...quality.scenario_generator import build_baseline_scenarios
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state.manager import StateManager
from . import analyze

log = get_logger("qa_agent.full_run")


def run(args: argparse.Namespace) -> int:
    rc = analyze.run(args)
    if rc != 0:
        return rc

    project = args.project
    root = project_root(project)
    sm = StateManager(project)

    strategy = sm.strategy()
    scenarios = build_baseline_scenarios(strategy)
    sm.save(scenarios)
    log.info("full-run: scenarios saved (%d entries)", len(scenarios.entries))

    pm = sm.project_map()
    generated, critique = run_generation_loop(root, scenarios, pm)
    sm.save(generated)
    sm.save(critique)
    log.info(
        "full-run: generated %d test files; critique score avg=%.1f",
        len(generated.entries),
        _avg([r.score for r in critique.results]),
    )

    log.info("full-run: execution + reporting phases not yet implemented (see ROADMAP.md)")
    return 0


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0
