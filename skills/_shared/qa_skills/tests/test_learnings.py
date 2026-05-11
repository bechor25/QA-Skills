"""validate_learnings tests — file IO via tmp_path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.learnings import validate_learnings, LEARNINGS_VERSION


def _write_learnings(pr: Path, data: dict) -> Path:
    qa = pr / ".qa-skills"
    qa.mkdir(parents=True, exist_ok=True)
    p = qa / "learnings.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_no_learnings_when_file_missing(tmp_path):
    result = validate_learnings(tmp_path)
    assert result["status"] == "no_learnings"
    assert result["priors"] == {c: [] for c in ("unit","api","ui","security","a11y","contract")}


def test_version_mismatch_returns_no_learnings(tmp_path):
    _write_learnings(tmp_path, {"version": "0.9", "vuln_patterns": [], "flaky_history": []})
    result = validate_learnings(tmp_path)
    assert result["status"] == "no_learnings"
    assert "version_mismatch" in result.get("reason", "")


def test_malformed_json_returns_error(tmp_path):
    qa = tmp_path / ".qa-skills"
    qa.mkdir()
    (qa / "learnings.json").write_text("{ not json }", encoding="utf-8")
    result = validate_learnings(tmp_path)
    assert result["status"] == "error"


def test_dismissed_entries_filtered_from_priors(tmp_path):
    # Create source file so it does not get dropped for path_gone
    src = tmp_path / "app" / "auth.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): pass", encoding="utf-8")

    import hashlib
    h = hashlib.sha256(src.read_bytes()).hexdigest()

    _write_learnings(tmp_path, {
        "version": LEARNINGS_VERSION,
        "vuln_patterns": [{
            "id": "v1", "rule": "x", "category": "security",
            "module_path": "app/auth.py", "module_hash": h,
            "tier": "confirmed", "user_status": "dismissed_intentional",
            "occurrences": 3, "evidence_runs": [], "last_seen": "2026-05-09T00:00:00Z",
        }],
        "flaky_history": [],
    })
    result = validate_learnings(tmp_path, now="2026-05-10T00:00:00Z")
    assert result["status"] == "completed"
    assert result["priors"]["security"] == []   # dismissed not in priors
    assert result["actions"]["filtered_dismissed"] == 1


def test_module_path_gone_drops_entry(tmp_path):
    _write_learnings(tmp_path, {
        "version": LEARNINGS_VERSION,
        "vuln_patterns": [{
            "id": "v1", "rule": "x", "category": "security",
            "module_path": "missing/file.py", "module_hash": "h",
            "tier": "candidate", "user_status": "open",
            "occurrences": 1, "evidence_runs": [], "last_seen": "2026-05-09T00:00:00Z",
        }],
        "flaky_history": [],
    })
    result = validate_learnings(tmp_path, now="2026-05-10T00:00:00Z")
    assert result["status"] == "completed"
    assert result["actions"]["filtered_unknown_module"] == 1
    assert result["priors"]["security"] == []


def test_module_hash_changed_demotes_confirmed(tmp_path):
    src = tmp_path / "app" / "auth.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def login(): pass", encoding="utf-8")

    _write_learnings(tmp_path, {
        "version": LEARNINGS_VERSION,
        "vuln_patterns": [{
            "id": "v1", "rule": "x", "category": "security",
            "module_path": "app/auth.py", "module_hash": "stale-hash",
            "tier": "confirmed", "user_status": "open",
            "occurrences": 5, "evidence_runs": ["r1","r2"],
            "last_seen": "2026-05-09T00:00:00Z",
        }],
        "flaky_history": [],
    })
    result = validate_learnings(tmp_path, now="2026-05-10T00:00:00Z", run_id="run-x")
    assert result["status"] == "completed"
    assert any(a["from"] == "confirmed" for a in result["actions"]["demoted"])
    # Entry now in priors as candidate
    assert result["priors"]["security"][0]["tier"] == "candidate"


def test_aged_out_entry_dropped(tmp_path):
    src = tmp_path / "app" / "auth.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x", encoding="utf-8")
    import hashlib
    h = hashlib.sha256(src.read_bytes()).hexdigest()

    _write_learnings(tmp_path, {
        "version": LEARNINGS_VERSION,
        "vuln_patterns": [{
            "id": "v1", "rule": "x", "category": "security",
            "module_path": "app/auth.py", "module_hash": h,
            "tier": "candidate", "user_status": "open",
            "occurrences": 1, "evidence_runs": [],
            "last_seen": "2026-01-01T00:00:00Z",
        }],
        "flaky_history": [],
    })
    result = validate_learnings(tmp_path, now="2026-05-10T00:00:00Z")
    assert any(d.get("reason") == "aged_out" for d in result["actions"]["dropped"])
    assert result["priors"]["security"] == []
