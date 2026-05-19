"""`qa-agent heal-rerun` — scoped re-execution + heal-ledger delta.

Same body as `qa-agent rerun` (reuses retry_engine + execute_all) but
also appends a `HealIterationRecord` to `heal_ledger.json` so the loop
predicate (`heal-status`) can see the pass-rate delta this iteration
produced. Defaults to single-worker determinism via the executors'
existing behaviour (Session-2 used workers:1 for reliable diagnosis).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from ...agent.execution_controller import execute_all
from ...agent.retry_engine import scope_paths
from ...healing.loop import baseline_pass_rate
from ...runtime.workspace import new_workspace
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.heal_rerun")


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    sm = StateManager(args.project)

    tests = sm.load(schemas.GeneratedTests)
    if not tests.entries:
        log.error("heal-rerun: no generated tests")
        return 1

    pass_before, total_before, rate_before = baseline_pass_rate(sm)

    paths = set(scope_paths(root, args.scope))
    if not paths:
        log.info("heal-rerun: scope=%s yielded 0 tests — nothing to do", args.scope)
        return 0

    scoped = schemas.GeneratedTests(
        built_at=datetime.now(timezone.utc),
        entries=[t for t in tests.entries if t.path in paths],
    )
    ws = new_workspace(args.project)
    log.info("heal-rerun: scope=%s — %d test(s), run=%s",
             args.scope, len(scoped.entries), ws.run_id)
    execute_all(root, scoped, ws.run_id, timeout=getattr(args, "timeout", 300))

    pass_after, total_after, rate_after = baseline_pass_rate(sm)

    ledger = sm.heal_ledger()
    iteration = (
        args.iteration if getattr(args, "iteration", None) is not None
        else len(ledger.records) + 1
    )
    rec = schemas.HealIterationRecord(
        iteration=iteration,
        run_id=ws.run_id,
        pass_before=pass_before,
        pass_after=pass_after,
        total=total_after or total_before,
        pass_rate_before=round(rate_before, 4),
        pass_rate_after=round(rate_after, 4),
        delta=round(rate_after - rate_before, 4),
        tier=getattr(args, "tier", "mixed"),
        finished_at=datetime.now(timezone.utc),
    )
    ledger.records.append(rec)
    sm.save(ledger)

    log.info("heal-rerun: iter %d pass %d->%d (%.1f%%->%.1f%%)",
             iteration, pass_before, pass_after,
             rate_before * 100, rate_after * 100)
    print(json.dumps({
        "iteration": iteration, "run_id": ws.run_id,
        "pass_before": pass_before, "pass_after": pass_after,
        "pass_rate_after": round(rate_after, 4),
        "delta": round(rate_after - rate_before, 4),
    }, indent=2))
    return 0
