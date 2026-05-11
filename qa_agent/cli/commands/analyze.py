"""`qa-agent analyze` — scan + build knowledge graph only.

In Phase 0 this is a stub: it writes a minimal project_map.json so the
state files are valid and downstream phases have something to read.
Phase 1 replaces the body with the real scanner pipeline.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.analyze")


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    log.info("analyze: project=%s", root)
    sm = StateManager(args.project)

    pm = schemas.ProjectMap(
        project_root=str(root),
        scanned_at=datetime.now(timezone.utc),
    )
    sm.save(pm)
    log.info("analyze: wrote %s", sm.path_for(schemas.ProjectMap))
    return 0
