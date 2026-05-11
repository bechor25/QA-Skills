"""agent_log tests — per-batch persistence + merged status collapse (B4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.agent_log import (
    agent_log_path,
    write_agent_output,
    write_merged_agent_output,
)


def test_agent_log_path_per_batch_zero_padded(tmp_path: Path):
    p = agent_log_path(tmp_path, "qa-api-test", batch_idx=5)
    assert p.name == "agent_output_qa-api-test_batch_005.json"


def test_agent_log_path_merged_has_no_batch_suffix(tmp_path: Path):
    p = agent_log_path(tmp_path, "qa-api-test")
    assert p.name == "agent_output_qa-api-test.json"


def test_write_agent_output_roundtrip(tmp_path: Path):
    result = {
        "agent": "qa-unit-test",
        "status": "passed",
        "outputs": [{"path": "tests/unit/svc/test_svc.py", "covers": ["app/svc.py"]}],
    }
    p = write_agent_output(tmp_path, "qa-unit-test", result, batch_idx=0)
    assert p.is_file()
    assert json.loads(p.read_text(encoding="utf-8")) == result


def test_write_agent_output_atomic_replaces(tmp_path: Path):
    """Second write completely replaces the first; no partial state."""
    write_agent_output(tmp_path, "qa-api-test", {"status": "partial", "outputs": []}, batch_idx=0)
    write_agent_output(tmp_path, "qa-api-test", {"status": "passed", "outputs": []}, batch_idx=0)
    p = agent_log_path(tmp_path, "qa-api-test", batch_idx=0)
    assert json.loads(p.read_text(encoding="utf-8"))["status"] == "passed"


def test_merged_status_passed_when_all_passed(tmp_path: Path):
    results = [
        {"status": "passed", "outputs": [{"path": "a"}]},
        {"status": "passed", "outputs": [{"path": "b"}]},
    ]
    p = write_merged_agent_output(tmp_path, "qa-api-test", results)
    merged = json.loads(p.read_text(encoding="utf-8"))
    assert merged["status"] == "passed"
    assert [o["path"] for o in merged["outputs"]] == ["a", "b"]
    assert merged["batches"] == [{"index": 0, "status": "passed"}, {"index": 1, "status": "passed"}]


def test_merged_status_partial_dominates_passed(tmp_path: Path):
    results = [
        {"status": "passed",  "outputs": []},
        {"status": "partial", "outputs": []},
    ]
    p = write_merged_agent_output(tmp_path, "qa-api-test", results)
    merged = json.loads(p.read_text(encoding="utf-8"))
    assert merged["status"] == "partial"


def test_merged_status_error_dominates_all(tmp_path: Path):
    results = [
        {"status": "passed",  "outputs": []},
        {"status": "partial", "outputs": []},
        {"status": "error",   "outputs": []},
    ]
    merged = json.loads(
        write_merged_agent_output(tmp_path, "qa-api-test", results).read_text(encoding="utf-8")
    )
    assert merged["status"] == "error"


def test_merged_skipped_status_recognized(tmp_path: Path):
    results = [
        {"status": "skipped:no_server", "outputs": []},
    ]
    merged = json.loads(
        write_merged_agent_output(tmp_path, "qa-ui-test", results).read_text(encoding="utf-8")
    )
    assert merged["status"] == "skipped"


def test_merged_aggregates_missing_items_dedup(tmp_path: Path):
    results = [
        {"status": "partial", "outputs": [], "missing_items": ["tests/a", "tests/b"]},
        {"status": "partial", "outputs": [], "missing_items": ["tests/b", "tests/c"]},
    ]
    merged = json.loads(
        write_merged_agent_output(tmp_path, "qa-api-test", results).read_text(encoding="utf-8")
    )
    assert merged["missing_items"] == ["tests/a", "tests/b", "tests/c"]


def test_merged_aggregates_warnings_dedup_and_sorted(tmp_path: Path):
    results = [
        {"status": "partial", "outputs": [], "warnings": ["w1", "w2"]},
        {"status": "partial", "outputs": [], "warnings": ["w2", "w3"]},
    ]
    merged = json.loads(
        write_merged_agent_output(tmp_path, "qa-api-test", results).read_text(encoding="utf-8")
    )
    assert merged["warnings"] == ["w1", "w2", "w3"]


def test_merged_handles_malformed_entries(tmp_path: Path):
    """Non-dict items get skipped; the merge does not crash."""
    results = [
        None,
        "string",
        {"status": "passed", "outputs": [{"path": "a"}]},
    ]
    merged = json.loads(
        write_merged_agent_output(tmp_path, "qa-api-test", results).read_text(encoding="utf-8")
    )
    assert [o["path"] for o in merged["outputs"]] == ["a"]
