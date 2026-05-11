"""validate_learnings tests — file IO via tmp_path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.learnings import (
    LEARNINGS_VERSION,
    PROMOTION_THRESHOLD,
    persist_learnings,
    validate_learnings,
)


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


# ---------------------------------------------------------------------------
# persist_learnings
# ---------------------------------------------------------------------------


def _vuln(category="security", module_path="src/auth/login.ts",
          rule="auth_other_user_resource", **extra) -> dict:
    out = {"category": category, "module_path": module_path, "rule": rule,
           "test_path": "tests/security/auth/login.security.test.ts::test_idor",
           "line_range": [10, 20],
           "module_hash": "a" * 64,
           "evidence_runs": []}
    out.update(extra)
    return out


def test_persist_creates_skeleton_on_first_run(tmp_path: Path):
    summary = persist_learnings(tmp_path, all_test_outputs=[], run_id="r1")
    lj = json.loads((tmp_path / ".qa-skills" / "learnings.json")
                    .read_text(encoding="utf-8"))
    assert lj["version"] == LEARNINGS_VERSION
    assert lj["runs_seen"] == 1
    assert lj["vuln_patterns"] == []
    assert summary["added_this_run"] == 0
    assert summary["vuln_patterns_total"] == 0


def test_persist_adds_new_vulnerability(tmp_path: Path):
    outputs = [{
        "agent":  "qa-security-test",
        "status": "passed",
        "outputs": [{
            "path": "tests/security/auth/login.security.test.ts",
            "vulnerabilities_found": [_vuln()],
        }],
    }]
    s = persist_learnings(tmp_path, all_test_outputs=outputs, run_id="r1")
    assert s["added_this_run"] == 1
    assert s["incremented_this_run"] == 0
    lj = json.loads((tmp_path / ".qa-skills" / "learnings.json")
                    .read_text(encoding="utf-8"))
    assert len(lj["vuln_patterns"]) == 1
    e = lj["vuln_patterns"][0]
    assert e["tier"] == "candidate"
    assert e["occurrences"] == 1
    assert e["source_agent"] == "qa-security-test"


def test_persist_increments_existing_vulnerability(tmp_path: Path):
    outputs = [{
        "agent": "qa-security-test",
        "outputs": [{"vulnerabilities_found": [_vuln()]}],
    }]
    persist_learnings(tmp_path, all_test_outputs=outputs, run_id="r1")
    s2 = persist_learnings(tmp_path, all_test_outputs=outputs, run_id="r2")
    assert s2["added_this_run"] == 0
    assert s2["incremented_this_run"] == 1
    lj = json.loads((tmp_path / ".qa-skills" / "learnings.json")
                    .read_text(encoding="utf-8"))
    assert lj["vuln_patterns"][0]["occurrences"] == 2
    assert set(lj["vuln_patterns"][0]["evidence_runs"]) == {"r1", "r2"}


def test_persist_promotes_after_threshold(tmp_path: Path):
    outputs = [{
        "agent": "qa-security-test",
        "outputs": [{"vulnerabilities_found": [_vuln()]}],
    }]
    promoted_seen = 0
    for i in range(PROMOTION_THRESHOLD):
        s = persist_learnings(tmp_path, all_test_outputs=outputs, run_id=f"r{i}")
        promoted_seen += s["promoted_this_run"]
    assert promoted_seen == 1
    lj = json.loads((tmp_path / ".qa-skills" / "learnings.json")
                    .read_text(encoding="utf-8"))
    assert lj["vuln_patterns"][0]["tier"] == "confirmed"


def test_persist_records_flaky_history(tmp_path: Path):
    persist_learnings(
        tmp_path,
        all_test_outputs=[],
        flaky_tests=[{"test_path": "tests/api/auth/login.api.test.ts::test_x",
                      "flake_count": 2}],
        run_id="r1",
    )
    lj = json.loads((tmp_path / ".qa-skills" / "learnings.json")
                    .read_text(encoding="utf-8"))
    assert len(lj["flaky_history"]) == 1
    assert lj["flaky_history"][0]["test_path"].endswith("::test_x")


def test_persist_skips_dismissed_intentional(tmp_path: Path):
    # Seed with a dismissed entry
    lj_path = tmp_path / ".qa-skills" / "learnings.json"
    lj_path.parent.mkdir(parents=True, exist_ok=True)
    finding = _vuln()
    # Compute the same id used by persist_learnings
    from qa_skills.learnings import _sha256
    fid = _sha256(finding["category"], finding["module_path"], finding["rule"])
    lj_path.write_text(json.dumps({
        "version": LEARNINGS_VERSION, "project_id": "x",
        "created_at": "2026-01-01T00:00:00Z", "last_updated": "2026-01-01T00:00:00Z",
        "runs_seen": 1,
        "vuln_patterns": [{
            **finding, "id": fid, "tier": "candidate", "occurrences": 1,
            "user_status": "dismissed_intentional", "evidence_runs": ["r0"],
            "first_seen": "2026-01-01T00:00:00Z", "last_seen": "2026-01-01T00:00:00Z",
        }],
        "flaky_history": [], "skip_history": [], "category_effectiveness": {},
    }))
    outputs = [{
        "agent": "qa-security-test",
        "outputs": [{"vulnerabilities_found": [finding]}],
    }]
    s = persist_learnings(tmp_path, all_test_outputs=outputs, run_id="r1")
    assert s["incremented_this_run"] == 0
    # Should still be present, untouched.
    lj = json.loads(lj_path.read_text(encoding="utf-8"))
    assert lj["vuln_patterns"][0]["occurrences"] == 1
    assert lj["vuln_patterns"][0]["user_status"] == "dismissed_intentional"


def test_persist_writes_category_effectiveness(tmp_path: Path):
    outputs = [{
        "agent": "qa-unit-test",
        "outputs": [
            {"tests_written": 5, "vulnerabilities_found": []},
            {"tests_written": 3, "vulnerabilities_found": []},
        ],
    }]
    persist_learnings(tmp_path, all_test_outputs=outputs, run_id="r1")
    lj = json.loads((tmp_path / ".qa-skills" / "learnings.json")
                    .read_text(encoding="utf-8"))
    eff = lj["category_effectiveness"]["unit"]
    assert eff["generated"] == 8
    assert eff["kept"] == 0
    assert eff["ratio"] == 0.0


def test_persist_appends_to_log(tmp_path: Path):
    outputs = [{
        "agent": "qa-security-test",
        "outputs": [{"vulnerabilities_found": [_vuln()]}],
    }]
    s = persist_learnings(tmp_path, all_test_outputs=outputs, run_id="r1")
    log_path = Path(s["log_path"])
    assert log_path.is_file()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert any('"action": "add"' in line for line in lines)
