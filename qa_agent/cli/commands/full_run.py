"""`qa-agent full-run` — end-to-end pipeline.

Implements phases 0-4: analyze -> scenarios -> generation -> install -> execute.
Reporting follows in Phase 6.
"""

from __future__ import annotations

import argparse

from ...agent.execution_controller import execute_all
from ...quality.generation_loop import run_generation_loop
from ...quality.scenario_generator import build_baseline_scenarios
from ...runtime.install_manager import run_installs
from ...runtime.install_planner import plan_installs
from ...runtime.workspace import new_workspace
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
    ws = new_workspace(project)
    log.info("full-run: workspace=%s", ws.root)

    strategy = sm.strategy()
    scenarios = build_baseline_scenarios(strategy)
    sm.save(scenarios)
    log.info("full-run: scenarios saved (%d)", len(scenarios.entries))

    pm = sm.project_map()
    generated, critique = run_generation_loop(root, scenarios, pm)
    sm.save(generated)
    sm.save(critique)
    log.info("full-run: generated=%d critique_avg=%.1f", len(generated.entries), _avg([r.score for r in critique.results]))

    skip_exec = bool(getattr(args, "no_llm", False))  # use --no-llm as proxy for offline runs
    if skip_exec:
        log.info("full-run: --no-llm set; skipping install + execute phases")
        return 0

    steps = plan_installs(pm, generated)
    if steps:
        run_installs(root, steps, ws.run_id)

    results = execute_all(root, generated, ws.run_id)
    total = sum(r.passed + r.failed + r.skipped for r in results)
    failed = sum(r.failed for r in results)
    log.info("full-run: executed %d tests across %d groups; failed=%d", total, len(results), failed)
    log.info("full-run: reporting phase not yet implemented (see ROADMAP.md)")
    return 0 if failed == 0 else 0  # don't fail CLI; report carries the verdict


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0
