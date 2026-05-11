"""`qa-agent report` — render the latest HTML report.

Stubbed in Phase 0 — implemented in Phase 6 (reporting).
"""

from __future__ import annotations

import argparse

from ...shared.logging import get_logger

log = get_logger("qa_agent.report")


def run(args: argparse.Namespace) -> int:
    log.info(
        "report: open_browser=%s — not yet implemented (see ROADMAP.md)",
        args.open_browser,
    )
    return 0
