"""`qa-agent rerun` — incremental re-execution via the retry engine."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from ...agent.execution_controller import execute_all
from ...agent.retry_engine import scope_paths
from ...runtime.workspace import new_workspace
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.rerun")


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    sm = StateManager(args.project)
    tests = sm.load(schemas.GeneratedTests)
    if not tests.entries:
        log.error("rerun: no generated tests; run `qa-agent full-run` first")
        return 1

    paths = set(scope_paths(root, args.scope))
    if not paths:
        log.info("rerun: scope=%s yielded 0 tests — nothing to do", args.scope)
        return 0
    log.info("rerun: scope=%s — %d test(s) to re-execute", args.scope, len(paths))

    scoped = schemas.GeneratedTests(
        built_at=datetime.now(timezone.utc),
        entries=[t for t in tests.entries if t.path in paths],
    )
    ws = new_workspace(args.project)
    results = execute_all(root, scoped, ws.run_id)
    failed = sum(r.failed for r in results)
    log.info("rerun: failed=%d across %d group(s)", failed, len(results))
    return 0
