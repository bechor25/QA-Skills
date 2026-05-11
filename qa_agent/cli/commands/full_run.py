"""`qa-agent full-run` — end-to-end pipeline.

In Phase 0 this is a stub that invokes `analyze` only. Phases 1-6 wire
in scanning → strategy → generation → execution → reporting.
"""

from __future__ import annotations

import argparse

from ...shared.logging import get_logger
from . import analyze

log = get_logger("qa_agent.full_run")


def run(args: argparse.Namespace) -> int:
    log.info("full-run: phase 0 (stub) — delegating to analyze")
    rc = analyze.run(args)
    if rc != 0:
        return rc
    log.info("full-run: remaining phases not yet implemented (see ROADMAP.md)")
    return 0
