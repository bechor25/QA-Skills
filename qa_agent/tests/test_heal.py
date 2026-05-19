"""Heal pipeline: clustering, loop predicate, patcher round-trip, scope gate."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from qa_agent.healing.cluster import cluster_failures
from qa_agent.healing.loop import heal_decision
from qa_agent.healing.patcher import (
    ScopeError,
    apply_patch,
    assert_in_scope,
    revert_iteration,
    _apply_unified_diff,
)
from qa_agent.state import schemas
from qa_agent.state.manager import StateManager


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------

def test_cluster_collapses_shared_auth_and_keeps_per_test_tail(tmp_path: Path):
    sm = StateManager(tmp_path)
    failures: list[schemas.HealFailureRecord] = []
    # 45 identical cross-capability 401s -> one systemic cluster
    for i in range(45):
        failures.append(schemas.HealFailureRecord(
            test_id=f"sc::cap{i % 5}::api::{i:02d}",
            test_path=f"tests/qa-agent/api/cap{i % 5}.spec.ts",
            status="failed",
            error_message="expected 200 to be 401 unauthorized",
            normalized_signature="expected # to be # unauthorized",
            failure_category="auth",
        ))
    # 10 distinct assertion failures -> per_test residue
    for i in range(10):
        failures.append(schemas.HealFailureRecord(
            test_id=f"sc::misc::api::{i:02d}",
            test_path=f"tests/qa-agent/api/misc{i}.spec.ts",
            status="failed",
            error_message=f"AssertionError: expected value{i} to equal other{i}",
            normalized_signature=f"assertionerror: expected value{i} to equal other{i}",
            failure_category="assertion",
        ))

    clusters = cluster_failures(failures, sm, run_id="r1")

    assert len(clusters.systemic) == 1
    sysc = clusters.systemic[0]
    assert sysc.tier == "systemic"
    assert sysc.shared_signal == "auth-storage-state"
    assert sysc.suggested_fix_kind == "harness"
    assert sysc.size == 45
    assert len(clusters.per_test) == 10
    assert all(c.tier == "per_test" and c.size == 1 for c in clusters.per_test)
    # back-references stamped onto the records
    assert all(f.cluster_id for f in failures)


def test_cluster_flags_prod_bug_and_excludes_from_systemic(tmp_path: Path):
    sm = StateManager(tmp_path)
    failures = [
        schemas.HealFailureRecord(
            test_id=f"sc::pay::api::{i:02d}",
            test_path="tests/qa-agent/api/pay.spec.ts",
            status="failed",
            error_message="Error: 500 internal server error — unhandled exception",
            normalized_signature="error: # internal server error unhandled exception",
            failure_category="unknown",
        )
        for i in range(3)
    ]
    clusters = cluster_failures(failures, sm, run_id="r1")
    assert clusters.systemic == []
    assert len(clusters.per_test) == 3
    assert all(c.is_prod_bug for c in clusters.per_test)


def test_cluster_triage_verdict_overrides_heuristic(tmp_path: Path):
    sm = StateManager(tmp_path)
    sm.save_triage(schemas.TriageVerdict(
        test_id="sc::auth::api::01", verdict="prod-bug",
        confidence=0.9, built_at=_now(),
    ))
    failures = [
        schemas.HealFailureRecord(
            test_id="sc::auth::api::01", test_path="tests/qa-agent/api/a.spec.ts",
            status="failed", error_message="401 unauthorized",
            normalized_signature="# unauthorized", failure_category="auth"),
        schemas.HealFailureRecord(
            test_id="sc::auth::api::02", test_path="tests/qa-agent/api/a.spec.ts",
            status="failed", error_message="401 unauthorized",
            normalized_signature="# unauthorized", failure_category="auth"),
    ]
    clusters = cluster_failures(failures, sm, run_id="r1")
    # prod-bug member poisons the cluster -> not auto-fixed
    assert clusters.systemic == []
    assert any(c.is_prod_bug for c in clusters.per_test)


# ---------------------------------------------------------------------
# Loop predicate
# ---------------------------------------------------------------------

def _seed_history(sm: StateManager, passed: int, failed: int, run_id="base"):
    h = schemas.ExecutionHistory(records=[schemas.ExecutionRecord(
        run_id=run_id, started_at=_now(), finished_at=_now(),
        category="api", passed=passed, failed=failed, skipped=0)])
    sm.save(h)


def _residue(sm: StateManager):
    # one un-attempted failure so _residue_all_exhausted is False
    sm.save(schemas.HealFailures(built_at=_now(), records=[
        schemas.HealFailureRecord(test_id="sc::x::api::01", status="failed")]))


def test_loop_baseline_when_no_iterations(tmp_path: Path):
    sm = StateManager(tmp_path)
    _seed_history(sm, 28, 72)
    d = heal_decision(sm)
    assert d["decision"] == "continue"
    assert d["iteration"] == 0
    assert d["pass_rate"] == pytest.approx(0.28)


def test_loop_cap_at_max_iterations(tmp_path: Path):
    sm = StateManager(tmp_path)
    _seed_history(sm, 50, 50)
    _residue(sm)
    recs = [schemas.HealIterationRecord(
        iteration=i, pass_before=40 + i, pass_after=41 + i, total=100,
        pass_rate_before=(40 + i) / 100, pass_rate_after=(41 + i) / 100,
        delta=0.01, finished_at=_now()) for i in range(1, 5)]
    sm.save(schemas.HealLedger(records=recs))
    assert heal_decision(sm)["decision"] == "cap"


def test_loop_rollback_on_regression(tmp_path: Path):
    sm = StateManager(tmp_path)
    _seed_history(sm, 50, 50)
    _residue(sm)
    sm.save(schemas.HealLedger(records=[schemas.HealIterationRecord(
        iteration=1, pass_before=60, pass_after=45, total=100,
        pass_rate_before=0.6, pass_rate_after=0.45, delta=-0.15,
        finished_at=_now())]))
    assert heal_decision(sm)["decision"] == "rollback"


def test_loop_plateau(tmp_path: Path):
    sm = StateManager(tmp_path)
    _seed_history(sm, 50, 50)
    _residue(sm)
    sm.save(schemas.HealLedger(records=[
        schemas.HealIterationRecord(
            iteration=1, pass_before=40, pass_after=60, total=100,
            pass_rate_before=0.4, pass_rate_after=0.6, delta=0.2,
            finished_at=_now()),
        schemas.HealIterationRecord(
            iteration=2, pass_before=60, pass_after=62, total=100,
            pass_rate_before=0.6, pass_rate_after=0.62, delta=0.02,
            finished_at=_now()),
    ]))
    assert heal_decision(sm)["decision"] == "plateau"


def test_loop_done_when_residue_exhausted(tmp_path: Path):
    sm = StateManager(tmp_path)
    _seed_history(sm, 90, 10)
    # no heal_failures saved -> residue empty -> nothing to gain
    sm.save(schemas.HealLedger(records=[schemas.HealIterationRecord(
        iteration=1, pass_before=50, pass_after=90, total=100,
        pass_rate_before=0.5, pass_rate_after=0.9, delta=0.4,
        finished_at=_now())]))
    assert heal_decision(sm)["decision"] == "done"


def test_loop_continue(tmp_path: Path):
    sm = StateManager(tmp_path)
    _seed_history(sm, 50, 50)
    _residue(sm)
    sm.save(schemas.HealLedger(records=[schemas.HealIterationRecord(
        iteration=1, pass_before=30, pass_after=55, total=100,
        pass_rate_before=0.3, pass_rate_after=0.55, delta=0.25,
        finished_at=_now())]))
    assert heal_decision(sm)["decision"] == "continue"


# ---------------------------------------------------------------------
# Patcher: scope gate, snapshot/apply/revert, diff apply
# ---------------------------------------------------------------------

def test_scope_gate_rejects_app_source_allows_harness():
    with pytest.raises(ScopeError):
        assert_in_scope("src/app.ts", "harness")
    with pytest.raises(ScopeError):
        assert_in_scope("apps/api/src/routes/auth.ts", "test")
    assert_in_scope("tests/qa-agent/global-setup.ts", "harness")
    assert_in_scope("playwright.config.ts", "config")
    assert_in_scope("package.json", "harness")


def test_apply_then_revert_created_file_deletes_it(tmp_path: Path):
    sm = StateManager(tmp_path)
    rel = "tests/qa-agent/global-setup.ts"
    res = apply_patch(tmp_path, sm, rel, "export default 1;\n",
                      iteration=1, run_id="r1", kind="harness")
    assert res["applied"] and res["created"]
    assert (tmp_path / rel).read_text() == "export default 1;\n"

    out = revert_iteration(tmp_path, sm, 1)
    assert out["reverted"]
    assert not (tmp_path / rel).exists()


def test_apply_then_revert_existing_file_restores_original(tmp_path: Path):
    sm = StateManager(tmp_path)
    rel = "tests/qa-agent/api/auth.spec.ts"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ORIGINAL\n", encoding="utf-8")

    apply_patch(tmp_path, sm, rel, "PATCHED\n",
                iteration=2, run_id="r1", kind="test")
    assert target.read_text() == "PATCHED\n"

    revert_iteration(tmp_path, sm, 2)
    assert target.read_text() == "ORIGINAL\n"


def test_apply_unified_diff_minimal():
    original = "line1\nline2\nline3\n"
    diff = (
        "--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n"
        " line1\n-line2\n+line2-fixed\n line3\n"
    )
    assert _apply_unified_diff(original, diff) == "line1\nline2-fixed\nline3\n"


def test_apply_unified_diff_context_mismatch_raises():
    with pytest.raises(ValueError):
        _apply_unified_diff("a\nb\n", "--- x\n+++ x\n@@ -1,1 +1,1 @@\n-zzz\n+q\n")
