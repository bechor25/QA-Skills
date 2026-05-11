"""`qa-agent state show|reset` — inspect or wipe project state."""

from __future__ import annotations

import argparse
import json
import shutil

from ...shared.logging import get_logger
from ...shared.paths import qa_data_dir, state_dir

log = get_logger("qa_agent.state")


def run(args: argparse.Namespace) -> int:
    if args.action == "show":
        return _show(args.project)
    if args.action == "reset":
        return _reset(args.project)
    return 2


def _show(project: str | None) -> int:
    d = state_dir(project)
    files = sorted(p.name for p in d.glob("*.json"))
    print(json.dumps({"state_dir": str(d), "files": files}, indent=2))
    return 0


def _reset(project: str | None) -> int:
    d = qa_data_dir(project)
    if d.exists():
        shutil.rmtree(d)
        log.info("state: removed %s", d)
    else:
        log.info("state: nothing to remove at %s", d)
    return 0
