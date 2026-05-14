"""`qa-agent run-tests` — execute the scaffolded + authored test suite.

Phase 8 of the agent-driven pipeline. Reads generated_tests.json (which
was populated by `scaffold` and then filled by qa-body-author),
optionally skips install (when the env is already prepared), and runs
the executors. Failures are written into execution_history.json for the
qa-triage sub-agent to consume.
"""

from __future__ import annotations

import argparse

from ...agent.execution_controller import execute_all
from ...runtime.install_manager import run_installs
from ...runtime.install_planner import plan_installs
from ...runtime.workspace import new_workspace
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.run_tests")


def run(args: argparse.Namespace) -> int:
    project = args.project
    root = project_root(project)
    sm = StateManager(project)
    ws = new_workspace(project)

    generated = sm.load(schemas.GeneratedTests)
    if not generated.entries:
        log.warning("run-tests: no generated tests found — did you run `scaffold`?")
        return 0

    if getattr(args, "probe_only", False):
        before = len(generated.entries)
        generated.entries = [e for e in generated.entries if "/_probe/" in e.path]
        log.info(
            "run-tests: --probe-only scoped to %d/%d probe tests",
            len(generated.entries),
            before,
        )
        if not generated.entries:
            log.warning("run-tests: --probe-only set but no probe tests found")
            return 0

    if getattr(args, "skip_install", False):
        log.info("run-tests: --skip-install set, assuming dependencies are ready")
    else:
        pm = sm.project_map()
        steps = plan_installs(pm, generated)
        if steps:
            run_installs(root, steps, ws.run_id)

    timeout = int(getattr(args, "timeout", 300))
    results = execute_all(root, generated, ws.run_id, timeout=timeout)
    total = sum(r.passed + r.failed + r.skipped for r in results)
    failed = sum(r.failed for r in results)
    log.info("run-tests: %d tests across %d groups (failed=%d run_id=%s)",
             total, len(results), failed, ws.run_id)
    log.info("run-tests: READY. Next: fan out qa-triage per failing test_id.")
    return 0
