"""`qa-agent rerun` — incremental re-execution.

Stubbed in Phase 0 — wired in Phase 4 (execution) + Phase 5 (retry engine).
"""

from __future__ import annotations

import argparse

from ...shared.logging import get_logger

log = get_logger("qa_agent.rerun")


def run(args: argparse.Namespace) -> int:
    log.info("rerun: scope=%s — not yet implemented (see ROADMAP.md)", args.scope)
    return 0
