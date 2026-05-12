"""`qa-agent prepare` — pre-LLM phases (scan + analyze + strategy + scanners).

This is phase 1–3 of the agent-driven pipeline. After it completes,
qa-master fans out to qa-enricher (one sub-agent per capability) to
fill `state/contracts/<capability>.json`.
"""

from __future__ import annotations

import argparse

from ...runtime.test_data import detect_test_data_plan
from ...scanners.ui_selectors import scan_ui_selectors
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state.manager import StateManager
from . import analyze

log = get_logger("qa_agent.prepare")


def run(args: argparse.Namespace) -> int:
    """Run analyze + UI selector scan + test-data plan detection."""
    rc = analyze.run(args)
    if rc != 0:
        return rc

    project = args.project
    root = project_root(project)
    sm = StateManager(project)

    pm = sm.project_map()
    kg = sm.knowledge_graph()

    selectors = scan_ui_selectors(root, pm, kg)
    sm.save(selectors)
    total = sum(len(v) for v in selectors.by_capability.values())
    log.info("prepare: ui_selectors saved (%d capabilities, %d selectors)",
             len(selectors.by_capability), total)

    plan = detect_test_data_plan(root, pm)
    sm.save(plan)
    log.info("prepare: test_data_plan orm=%s strategy=%s", plan.orm, plan.strategy)

    strategy = sm.strategy()
    log.info(
        "prepare: READY. Next: fan out qa-enricher per capability (%d) "
        "to write state/contracts/<cap>.json.",
        len(strategy.entries),
    )
    return 0
