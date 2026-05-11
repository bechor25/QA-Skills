"""driver tests — Task seam, disk verification, retry-once, run-context."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from qa_skills.driver import (
    RetryResult,
    TaskError,
    TaskTimeout,
    atomic_write_json,
    build_run_context,
    now_iso,
    phase_checkpoint,
    retry_once,
    task_subprocess,
    verify_on_disk,
    write_checkpoint,
)


# ---------------------------------------------------------------------------
# atomic_write_json
# ---------------------------------------------------------------------------


def test_atomic_write_json_writes_pretty_json(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1, "b": [2, 3]})
    text = target.read_text(encoding="utf-8")
    assert json.loads(text) == {"a": 1, "b": [2, 3]}
    assert text.endswith("\n")


def test_atomic_write_json_leaves_no_temp_files(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"x": 1})
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == []


# ---------------------------------------------------------------------------
# verify_on_disk
# ---------------------------------------------------------------------------


def test_verify_on_disk_returns_none_when_missing(tmp_path: Path):
    assert verify_on_disk(tmp_path / "nope.json") is None


def test_verify_on_disk_returns_none_when_malformed(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {")
    assert verify_on_disk(bad) is None


def test_verify_on_disk_returns_parsed_dict(tmp_path: Path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"k": "v"}))
    assert verify_on_disk(good) == {"k": "v"}


def test_verify_on_disk_returns_none_on_directory(tmp_path: Path):
    sub = tmp_path / "dir"
    sub.mkdir()
    assert verify_on_disk(sub) is None


# ---------------------------------------------------------------------------
# task_subprocess — runtime seam (uses mock to avoid spawning claude)
# ---------------------------------------------------------------------------


def test_task_subprocess_parses_stdout_json():
    fake_completed = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout='{"agent":"x","status":"ok"}', stderr=""
    )
    with patch("qa_skills.driver.subprocess.run", return_value=fake_completed):
        out = task_subprocess("qa-unit-test", {"foo": "bar"})
    assert out == {"agent": "x", "status": "ok"}


def test_task_subprocess_raises_on_nonzero_exit():
    fake_completed = subprocess.CompletedProcess(
        args=["claude"], returncode=1, stdout="", stderr="boom"
    )
    with patch("qa_skills.driver.subprocess.run", return_value=fake_completed):
        with pytest.raises(TaskError) as excinfo:
            task_subprocess("qa-unit-test", {})
    assert "exited 1" in str(excinfo.value)


def test_task_subprocess_raises_on_timeout():
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    with patch("qa_skills.driver.subprocess.run", side_effect=boom):
        with pytest.raises(TaskTimeout):
            task_subprocess("qa-unit-test", {}, timeout=1)


def test_task_subprocess_raises_on_unparseable_stdout():
    fake_completed = subprocess.CompletedProcess(
        args=["claude"], returncode=0, stdout="not json", stderr=""
    )
    with patch("qa_skills.driver.subprocess.run", return_value=fake_completed):
        with pytest.raises(TaskError) as excinfo:
            task_subprocess("qa-unit-test", {})
    assert "not JSON" in str(excinfo.value)


def test_task_subprocess_raises_on_missing_binary():
    with patch("qa_skills.driver.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(TaskError) as excinfo:
            task_subprocess("qa-unit-test", {}, claude_bin="nonexistent-bin")
    assert "claude binary not found" in str(excinfo.value)


# ---------------------------------------------------------------------------
# retry_once — pattern central to driver enforcement
# ---------------------------------------------------------------------------


def test_retry_once_succeeds_on_first_attempt(tmp_path: Path):
    artifact = tmp_path / "brief.json"

    def stub(agent: str, payload: dict) -> dict:
        artifact.write_text(json.dumps({"briefs": [{"x": 1}]}))
        return {"agent": agent, "status": "ok"}

    r = retry_once(
        stub,
        agent="qa-domain-analyzer",
        payload={"cat": "unit"},
        artifact_path=artifact,
        on_failure_prompt_suffix="please write the file",
    )
    assert r.ok
    assert r.attempts == 1
    assert r.artifact == {"briefs": [{"x": 1}]}


def test_retry_once_succeeds_on_second_attempt(tmp_path: Path):
    artifact = tmp_path / "brief.json"
    calls = []

    def stub(agent: str, payload: dict) -> dict:
        calls.append(dict(payload))
        if len(calls) == 2:
            artifact.write_text(json.dumps({"briefs": [{"x": 2}]}))
        return {"agent": agent, "status": "ok"}

    r = retry_once(
        stub,
        agent="qa-domain-analyzer",
        payload={"cat": "unit"},
        artifact_path=artifact,
        on_failure_prompt_suffix="please write the file",
    )
    assert r.ok
    assert r.attempts == 2
    assert r.artifact == {"briefs": [{"x": 2}]}
    # second call must include the retry_hint key
    assert calls[0].get("retry_hint") is None
    assert calls[1].get("retry_hint") == "please write the file"


def test_retry_once_returns_failure_when_both_attempts_fail(tmp_path: Path):
    artifact = tmp_path / "brief.json"

    def stub(agent: str, payload: dict) -> dict:
        return {"agent": agent, "status": "ok"}

    r = retry_once(
        stub,
        agent="qa-domain-analyzer",
        payload={"cat": "unit"},
        artifact_path=artifact,
        on_failure_prompt_suffix="please write the file",
    )
    assert not r.ok
    assert r.attempts == 2
    assert r.artifact is None


def test_retry_once_swallows_task_error_into_last_result(tmp_path: Path):
    artifact = tmp_path / "brief.json"

    def stub(agent: str, payload: dict) -> dict:
        raise TaskError("boom")

    r = retry_once(
        stub,
        agent="qa-domain-analyzer",
        payload={"cat": "unit"},
        artifact_path=artifact,
        on_failure_prompt_suffix="please write the file",
    )
    assert not r.ok
    assert "task_error:boom" in r.last_result["reason"]


# ---------------------------------------------------------------------------
# build_run_context — Phase 0 shape + side effects
# ---------------------------------------------------------------------------


def test_build_run_context_creates_directories(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    rc = build_run_context(project_root=project, locale="he", mode="auto")
    assert Path(rc["checkpoint_dir"]).is_dir()
    assert Path(rc["logs_dir"]).is_dir()
    assert Path(rc["reports_dir"]).is_dir()
    assert Path(rc["logs_dir"]).name == rc["run_id"]


def test_build_run_context_paths_are_absolute(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    rc = build_run_context(project_root=project)
    for key in ("project_root", "checkpoint_dir", "logs_dir", "reports_dir",
                "analysis_path", "strategy_path", "expected_files_path",
                "state_path"):
        assert Path(rc[key]).is_absolute(), f"{key} not absolute: {rc[key]}"


def test_build_run_context_accepts_explicit_run_id(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, run_id="abc-123")
    assert rc["run_id"] == "abc-123"
    assert rc["logs_dir"].endswith("/abc-123")


def test_build_run_context_idempotent_directory_creation(tmp_path: Path):
    rc1 = build_run_context(project_root=tmp_path, run_id="same")
    rc2 = build_run_context(project_root=tmp_path, run_id="same")
    assert rc1["logs_dir"] == rc2["logs_dir"]


def test_build_run_context_preserves_categories_filter(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, categories=["unit", "api"])
    assert rc["categories"] == ["unit", "api"]


# ---------------------------------------------------------------------------
# write_checkpoint / phase_checkpoint
# ---------------------------------------------------------------------------


def test_write_checkpoint_writes_atomic_json(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, run_id="r1")
    path = write_checkpoint(rc, phase=2, phase_name="strategy")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "r1"
    assert data["phase"] == 2
    assert data["phase_name"] == "strategy"
    assert data["completed"] is False
    assert "strategy" in data["completed_skills"]


def test_write_checkpoint_appends_to_completed_skills(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, run_id="r2")
    write_checkpoint(rc, phase=1, phase_name="scan")
    write_checkpoint(rc, phase=2, phase_name="strategy")
    data = json.loads((Path(rc["checkpoint_dir"]) / "run.json").read_text())
    assert data["completed_skills"] == ["scan", "strategy"]


def test_write_checkpoint_dedupes_skill_name(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, run_id="r3")
    write_checkpoint(rc, phase=1, phase_name="scan")
    write_checkpoint(rc, phase=1, phase_name="scan")
    data = json.loads((Path(rc["checkpoint_dir"]) / "run.json").read_text())
    assert data["completed_skills"] == ["scan"]


def test_phase_checkpoint_never_completes(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, run_id="r4")
    phase_checkpoint(rc, phase=2.5, name="strategy")
    data = json.loads((Path(rc["checkpoint_dir"]) / "run.json").read_text())
    assert data["completed"] is False
    assert data["phase"] == 2.5


def test_write_checkpoint_accepts_completed_true(tmp_path: Path):
    rc = build_run_context(project_root=tmp_path, run_id="r5")
    write_checkpoint(rc, phase=9, phase_name="final_gate", completed=True)
    data = json.loads((Path(rc["checkpoint_dir"]) / "run.json").read_text())
    assert data["completed"] is True


# ---------------------------------------------------------------------------
# now_iso — format guard
# ---------------------------------------------------------------------------


def test_now_iso_format():
    s = now_iso()
    # YYYY-MM-DDTHH:MM:SSZ
    assert len(s) == 20
    assert s.endswith("Z")
    assert s[4] == "-" and s[7] == "-" and s[10] == "T"
