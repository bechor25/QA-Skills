"""`qa-agent heal-status` — emit the loop decision JSON.

Read-only. Mirrors `retry-decide`: Python computes the stop predicate,
the test-fixer skill parses the JSON and drives the loop. Never mutates
state.
"""

from __future__ import annotations

import argparse
import json

from ...healing.loop import heal_decision
from ...shared.logging import get_logger
from ...state.manager import StateManager

log = get_logger("qa_agent.heal_status")


def run(args: argparse.Namespace) -> int:
    sm = StateManager(args.project)
    decision = heal_decision(sm)
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0
