"""Heal loop-control predicate.

Pure decision function — `heal-status` calls it and prints the result;
the skill drives the loop. Mirrors the `retry_budget.decide` /
`retry-decide` split (Python decides, the orchestrator loops).

Stop predicate (highest-priority match wins):

  rollback : last iteration lowered the pass count vs its own start
  cap      : max_iterations reached
  done     : pass_rate == 1.0, OR no residue worth retrying
             (every still-failing test is budget-exhausted or frozen)
  plateau  : >=2 iterations and the last gain < plateau_threshold
  continue : otherwise

Baseline (iteration 0) = the latest pre-heal ExecutionHistory aggregate
so the first systemic iteration is measured against the original
28.6%-style pass-rate, not against itself.
"""

from __future__ import annotations

from ..state import schemas
from ..state.manager import StateManager


def _latest_run_aggregate(history: schemas.ExecutionHistory) -> tuple[int, int]:
    """Return (passed, total) for the most recent run_id in history."""
    if not history.records:
        return 0, 0
    last_run = history.records[-1].run_id
    passed = total = 0
    for rec in reversed(history.records):
        if rec.run_id != last_run:
            break
        passed += rec.passed
        total += rec.passed + rec.failed + rec.skipped
    return passed, total


def baseline_pass_rate(sm: StateManager) -> tuple[int, int, float]:
    passed, total = _latest_run_aggregate(sm.execution_history())
    return passed, total, (passed / total if total else 0.0)


def _residue_all_exhausted(sm: StateManager) -> bool:
    """True when every remaining failing test is budget-exhausted or
    carries a frozen prod-bug/infra verdict — nothing left to gain."""
    failures = sm.heal_failures().records
    if not failures:
        return True
    budget = sm.load(schemas.RetryBudgetState)
    by_id = {e.test_id: e for e in budget.entries}
    for f in failures:
        e = by_id.get(f.test_id)
        if e is None:
            return False  # never attempted — still worth a pass
        if e.frozen_verdict in {"prod-bug", "infra"}:
            continue
        if e.attempts < budget.max_attempts:
            return False
    return True


def _collapse_iterations(recs: list[schemas.HealIterationRecord]) -> list[dict]:
    """Collapse the ledger to one logical step per distinct iteration.

    The skill calls `heal-rerun` twice per loop iteration (`systemic`
    then `per_test`), so 2 ledger rows can share one `iteration`. The
    iteration's effective state = its **last** row (per_test runs after
    systemic); its starting point = its **first** row's `pass_before`.
    `iteration == 0` is the H0 baseline row and is not a loop iteration.
    """
    by_iter: dict[int, list[schemas.HealIterationRecord]] = {}
    for r in recs:
        if r.iteration < 1:
            continue
        by_iter.setdefault(r.iteration, []).append(r)
    out: list[dict] = []
    for it in sorted(by_iter):
        rows = by_iter[it]
        first, last = rows[0], rows[-1]
        out.append({
            "iteration": it,
            "pass_before": first.pass_before,
            "pass_after": last.pass_after,
            "pass_rate_after": last.pass_rate_after,
            "total": last.total,
            "rolled_back": any(x.rolled_back for x in rows),
        })
    return out


def heal_decision(sm: StateManager) -> dict:
    """Return the loop decision JSON for `heal-status`.

    Counts **distinct loop iterations**, not ledger rows, so the
    `max_iterations` cap and plateau check reflect actual heal passes.
    """
    ledger = sm.heal_ledger()
    steps = _collapse_iterations(ledger.records)
    n = len(steps)

    base_passed, base_total, base_rate = baseline_pass_rate(sm)

    if n == 0:
        return {
            "decision": "continue",
            "iteration": 0,
            "pass_rate": round(base_rate, 4),
            "prev_pass_rate": round(base_rate, 4),
            "delta": 0.0,
            "max_iterations": ledger.max_iterations,
            "reason": f"baseline {base_passed}/{base_total} "
                      f"({base_rate:.1%}) — no heal iterations yet",
        }

    cur = steps[-1]
    prev_rate = steps[-2]["pass_rate_after"] if n >= 2 else base_rate
    pass_rate = cur["pass_rate_after"]
    delta = pass_rate - prev_rate

    def out(decision: str, reason: str) -> dict:
        return {
            "decision": decision,
            "iteration": n,
            "pass_rate": round(pass_rate, 4),
            "prev_pass_rate": round(prev_rate, 4),
            "delta": round(delta, 4),
            "max_iterations": ledger.max_iterations,
            "reason": reason,
        }

    if cur["pass_after"] < cur["pass_before"] and not cur["rolled_back"]:
        return out("rollback",
                   f"iteration {cur['iteration']} regressed "
                   f"({cur['pass_before']}->{cur['pass_after']}) — revert it")
    if n >= ledger.max_iterations:
        return out("cap", f"max_iterations ({ledger.max_iterations}) reached")
    if pass_rate >= 1.0:
        return out("done", "100% pass-rate")
    if _residue_all_exhausted(sm):
        return out("done", "residue budget-exhausted or frozen — nothing to gain")
    if n >= 2 and delta < ledger.plateau_threshold:
        return out("plateau",
                   f"gain {delta:.1%} < threshold "
                   f"{ledger.plateau_threshold:.0%}")
    return out("continue",
               f"gain {delta:.1%} >= {ledger.plateau_threshold:.0%}; "
               f"{n}/{ledger.max_iterations} iterations used")
