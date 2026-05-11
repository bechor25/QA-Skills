"""final_gate tests — focus on stub-content detection (A1).

The other checks (artifacts, UI proof, learnings audit) exercise filesystem
state that lives outside this unit-test sandbox; we exercise them via a small
report_data fixture and a tmp project root.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.final_gate import run_final_gate
from qa_skills.stub_markers import STUB_MARKERS, is_stub


# ---------- stub_markers basic ----------

def test_is_stub_detects_auto_generated_signature():
    assert is_stub("// Auto-generated stub. Replace.\n")


def test_is_stub_detects_tautological_assertion():
    assert is_stub("it('works', () => { expect(true).toBe(true); });")


def test_is_stub_detects_python_placeholder():
    assert is_stub("def test_thing():\n    assert True  # placeholder\n")


def test_is_stub_false_on_real_test():
    body = (
        "import pytest\n"
        "def test_login_returns_token():\n"
        "    res = client.post('/login', json={'u':'a','p':'b'})\n"
        "    assert res.status_code == 200\n"
        "    assert 'token' in res.json()\n"
    )
    assert not is_stub(body)


def test_stub_markers_constant_is_non_empty():
    assert STUB_MARKERS, "STUB_MARKERS tuple must not be empty"


# ---------- final_gate 9f integration ----------


def _write_min_report(tmp_path: Path, files_by_cat: dict[str, list[str]]) -> Path:
    """Write a minimal report-data + the four required artifacts."""
    (tmp_path / "test-state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "test-reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "test-reports" / "report-x.html").write_text("<html/>", encoding="utf-8")
    (tmp_path / ".qa-skills" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".qa-skills" / "checkpoints" / "run.json").write_text("{}", encoding="utf-8")

    report = {
        "coverage_by_category": {
            cat: {"status": "passed", "files": files}
            for cat, files in files_by_cat.items()
        }
    }
    rd = tmp_path / "test-reports" / "report-data.json"
    rd.write_text(json.dumps(report), encoding="utf-8")
    return rd


def test_9f_emits_warning_for_stub_file(tmp_path):
    test_file = tmp_path / "tests" / "api" / "auth" / "test_login.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "# Auto-generated stub. Replace.\n"
        "def test_placeholder():\n"
        "    assert True  # placeholder\n",
        encoding="utf-8",
    )

    rd = _write_min_report(tmp_path, {"api": ["tests/api/auth/test_login.py"]})
    result = run_final_gate(rd, tmp_path, run_id="r1")

    assert result["status"] == "partial"
    assert any(
        w.startswith("stub_content:api:tests/api/auth/test_login.py")
        for w in result["warnings"]
    ), result["warnings"]


def test_9f_no_warning_for_real_file(tmp_path):
    test_file = tmp_path / "tests" / "api" / "auth" / "test_login.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "from fastapi.testclient import TestClient\n"
        "def test_login_ok(client):\n"
        "    res = client.post('/login', json={'u':'a','p':'b'})\n"
        "    assert res.status_code == 200\n",
        encoding="utf-8",
    )

    rd = _write_min_report(tmp_path, {"api": ["tests/api/auth/test_login.py"]})
    result = run_final_gate(rd, tmp_path, run_id="r1")

    assert not any(w.startswith("stub_content:") for w in result["warnings"])


def test_9f_empty_files_list_no_warning(tmp_path):
    rd = _write_min_report(tmp_path, {"api": []})
    result = run_final_gate(rd, tmp_path, run_id="r1")
    assert not any(w.startswith("stub_content:") for w in result["warnings"])


def test_9f_missing_file_ignored(tmp_path):
    """Referenced-but-missing test file should NOT raise; just skip."""
    rd = _write_min_report(tmp_path, {"api": ["tests/api/ghost/test_missing.py"]})
    result = run_final_gate(rd, tmp_path, run_id="r1")
    assert not any(w.startswith("stub_content:") for w in result["warnings"])


def test_9f_mixed_categories_partial_status(tmp_path):
    real = tmp_path / "tests" / "unit" / "svc" / "test_real.py"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text(
        "def test_real():\n    assert sum([1,2,3]) == 6\n", encoding="utf-8"
    )

    stub = tmp_path / "tests" / "ui" / "Home" / "Home.spec.ts"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(
        "// Auto-generated stub. Replace.\n"
        "test('home placeholder', () => { expect(true).toBe(true); });\n",
        encoding="utf-8",
    )

    rd = _write_min_report(
        tmp_path,
        {
            "unit": ["tests/unit/svc/test_real.py"],
            "ui": ["tests/ui/Home/Home.spec.ts"],
        },
    )
    result = run_final_gate(rd, tmp_path, run_id="r1")

    assert result["status"] == "partial"
    stub_warnings = [w for w in result["warnings"] if w.startswith("stub_content:")]
    assert len(stub_warnings) == 1
    assert "ui:tests/ui/Home/Home.spec.ts" in stub_warnings[0]
