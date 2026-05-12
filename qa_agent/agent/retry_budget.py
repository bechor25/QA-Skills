"""Per-test retry budget with verdict gating.

The orchestrator (qa-master) calls into this module after every test
run + triage cycle to decide which tests deserve another attempt.

Decision rules (max_attempts = 2 by default):
    verdict=test-bug : retry if attempts < max
    verdict=flaky    : retry if attempts < max
    verdict=prod-bug : halt — never retry, surface to report
    verdict=infra    : halt — surface to report
    no verdict yet   : retry once (triage didn't run for this test)

Persistence: state/retry_budget.json. One entry per test_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from ..shared.logging import get_logger
from ..state import schemas
from ..state.manager import StateManager

log = get_logger("qa_agent.agent.retry_budget")


@dataclass(slots=True)
class RetryDecision:
    test_id: str
    should_retry: bool
    attempts_used: int
    reason: str
    verdict: str = ""


def decide(
    sm: StateManager,
    failing_test_ids: Iterable[str],
    run_id: str,
) -> list[RetryDecision]:
    """For each failing test, return a RetryDecision. Persists attempt counts."""
    state = sm.load(schemas.RetryBudgetState)
    by_id = {e.test_id: e for e in state.entries}
    out: list[RetryDecision] = []

    for tid in failing_test_ids:
        entry = by_id.get(tid)
        if entry is None:
            entry = schemas.RetryEntry(test_id=tid, last_seen=_now())
            state.entries.append(entry)
            by_id[tid] = entry

        verdict = _read_verdict(sm, tid)
        decision = _decide_one(entry, verdict, state.max_attempts)
        out.append(RetryDecision(
            test_id=tid,
            should_retry=decision.should_retry,
            attempts_used=entry.attempts,
            reason=decision.reason,
            verdict=verdict,
        ))

        if decision.should_retry:
            entry.attempts += 1
            entry.last_run_id = run_id
            entry.last_seen = _now()
        else:
            entry.frozen_verdict = verdict or entry.frozen_verdict
            entry.last_seen = _now()

    sm.save(state)
    log.info("retry-budget: %d decisions (retry=%d halt=%d)",
             len(out), sum(1 for d in out if d.should_retry),
             sum(1 for d in out if not d.should_retry))
    return out


# ---------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------

@dataclass(slots=True)
class _Inner:
    should_retry: bool
    reason: str


def _decide_one(entry: schemas.RetryEntry, verdict: str, max_attempts: int) -> _Inner:
    if entry.frozen_verdict in {"prod-bug", "infra"}:
        return _Inner(False, f"frozen verdict={entry.frozen_verdict}")
    if entry.attempts >= max_attempts:
        return _Inner(False, f"budget exhausted ({entry.attempts}/{max_attempts})")
    if verdict == "prod-bug":
        return _Inner(False, "verdict=prod-bug — halting retries, will be reported")
    if verdict == "infra":
        return _Inner(False, "verdict=infra — halting retries, env needs operator attention")
    if verdict in {"test-bug", "flaky", ""}:
        return _Inner(True, f"verdict={verdict or 'unknown'} — retry within budget")
    return _Inner(False, f"unknown verdict={verdict}")


def _read_verdict(sm: StateManager, test_id: str) -> str:
    v = sm.load_triage(test_id)
    return v.verdict if v else ""


def _now() -> datetime:
    return datetime.now(timezone.utc)
