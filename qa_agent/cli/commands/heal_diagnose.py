"""`qa-agent heal-diagnose` — run the failed scope, capture structured
per-test failures, and root-cause-cluster them.

Fills the gap that PerTestRecords are never persisted as state today:
writes `heal_failures.json` (structured) + `heal_clusters.json` (systemic
vs per_test). Works with OR without prior triage (`critique/*.json`).

`--no-run` reparses the latest run's per-test logs instead of executing
(degraded mode — useful when the suite is slow or the server is down).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ...agent.execution_controller import execute_all
from ...agent.retry_engine import scope_paths
from ...executors.base import PerTestRecord
from ...healing.cluster import cluster_failures, to_failure_records
from ...runtime.workspace import latest_run, new_workspace
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.heal_diagnose")


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    sm = StateManager(args.project)

    tests = sm.load(schemas.GeneratedTests)
    if not tests.entries:
        log.error("heal-diagnose: no generated tests; run `qa-agent full-run` first")
        return 1
    path_to_scenario = {e.path: e.scenario_id for e in tests.entries}

    if getattr(args, "no_run", False):
        ws = latest_run(args.project)
        if ws is None:
            log.error("heal-diagnose: --no-run but no prior run found")
            return 1
        run_id = ws.run_id
        records = _records_from_logs(ws.logs)
        log.info("heal-diagnose: --no-run reparsed %d records from %s",
                 len(records), run_id)
    else:
        failed_paths = set(scope_paths(root, "failed"))
        if not failed_paths:
            log.info("heal-diagnose: 0 failing tests in latest run — nothing to do")
            sm.save(schemas.HealClusters(built_at=datetime.now(timezone.utc)))
            print(json.dumps({"systemic": 0, "per_test": 0, "failures": 0}, indent=2))
            return 0
        scoped = schemas.GeneratedTests(
            built_at=datetime.now(timezone.utc),
            entries=[t for t in tests.entries if t.path in failed_paths],
        )
        ws = new_workspace(args.project)
        run_id = ws.run_id
        results = execute_all(root, scoped, run_id, timeout=getattr(args, "timeout", 300))
        records = [r for res in results for r in res.per_test_records]

    failures = to_failure_records(records, path_to_scenario)
    clusters = cluster_failures(failures, sm, run_id)

    sm.save(schemas.HealFailures(
        built_at=datetime.now(timezone.utc),
        run_id=run_id,
        records=failures,
    ))
    sm.save(clusters)

    summary = {
        "run_id": run_id,
        "failures": len(failures),
        "systemic": len(clusters.systemic),
        "per_test": len(clusters.per_test),
        "prod_bug_per_test": sum(1 for c in clusters.per_test if c.is_prod_bug),
        "systemic_clusters": [
            {
                "cluster_id": c.cluster_id,
                "signal": c.shared_signal,
                "fix_kind": c.suggested_fix_kind,
                "target": c.suggested_target,
                "size": c.size,
                "rationale": c.rationale,
            }
            for c in clusters.systemic
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------
# --no-run: reparse runs/<id>/logs/<safe>.log written by persist_per_test_logs
# ---------------------------------------------------------------------

def _records_from_logs(logs_dir: Path) -> list[PerTestRecord]:
    if not logs_dir.exists():
        return []
    out: list[PerTestRecord] = []
    for lf in sorted(logs_dir.glob("*.log")):
        if lf.name.startswith("_"):  # combined runner log, skip
            continue
        out.append(_parse_log(lf.read_text(encoding="utf-8", errors="ignore")))
    return [r for r in out if r.status not in {"passed", "skipped"}]


def _parse_log(text: str) -> PerTestRecord:
    meta: dict[str, str] = {}
    msg = stack = ""
    section = None
    for line in text.splitlines():
        if line.startswith("=== error message ==="):
            section = "msg"; continue
        if line.startswith("=== stack trace ==="):
            section = "stack"; continue
        if section == "msg":
            msg += line + "\n"
        elif section == "stack":
            stack += line + "\n"
        elif ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return PerTestRecord(
        test_id=meta.get("test_id", "unknown"),
        file=meta.get("file", ""),
        title=meta.get("title", ""),
        status=meta.get("status", "failed"),
        duration_ms=float(meta.get("duration_ms", 0) or 0),
        error_message=msg.strip(),
        error_stack=stack.strip(),
    )
