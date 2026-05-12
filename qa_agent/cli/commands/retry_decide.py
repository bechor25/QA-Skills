"""`qa-agent retry-decide` — emit retry decisions after triage.

Reads the latest execution_history failures, looks up each test's
triage verdict (state/critique/<test_id>.json) and the running retry
budget, and prints a JSON array of decisions to stdout. qa-master
parses the output to know which tests to re-run.

Output schema:
    [
      {"test_id": "...", "should_retry": true,
       "attempts_used": 1, "reason": "...", "verdict": "test-bug"},
      ...
    ]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...agent.retry_budget import decide
from ...runtime.workspace import latest_run_id
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.retry_decide")


def run(args: argparse.Namespace) -> int:
    project = args.project
    root = project_root(project)
    sm = StateManager(project)

    history = sm.load(schemas.ExecutionHistory)
    failing_paths = _failing_paths_latest_run(history)
    if not failing_paths:
        print("[]")
        return 0

    generated = sm.load(schemas.GeneratedTests)
    path_to_id = {e.path: e.scenario_id for e in generated.entries}
    failing_ids: list[str] = []
    for p in failing_paths:
        tid = path_to_id.get(p)
        if tid:
            failing_ids.append(tid)
        else:
            log.warning("retry-decide: no scenario_id for failing path %s", p)

    run_id = latest_run_id(root) or ""
    decisions = decide(sm, failing_ids, run_id)
    out = [
        {
            "test_id": d.test_id,
            "should_retry": d.should_retry,
            "attempts_used": d.attempts_used,
            "reason": d.reason,
            "verdict": d.verdict,
        }
        for d in decisions
    ]
    print(json.dumps(out, indent=2))
    return 0


def _failing_paths_latest_run(history: schemas.ExecutionHistory) -> list[str]:
    if not history.records:
        return []
    last_run = history.records[-1].run_id
    paths: set[str] = set()
    for rec in reversed(history.records):
        if rec.run_id != last_run:
            break
        if rec.failed:
            paths.update(rec.test_files)
    return sorted(paths)
