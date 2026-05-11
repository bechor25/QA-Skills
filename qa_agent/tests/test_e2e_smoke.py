"""End-to-end smoke test against a tiny FastAPI fixture.

Runs `qa-agent full-run --no-llm` so no real installs / executors fire
and the pipeline stays hermetic. Asserts that every state file exists,
the HTML report is written, and the quality score is computed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from qa_agent.cli.commands import full_run, report


def _seed_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["fastapi"]\n',
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        'from fastapi import FastAPI\n'
        'app = FastAPI()\n\n'
        '@app.post("/login")\nasync def login(): return {"token": "x"}\n\n'
        '@app.post("/payments/charge")\nasync def charge(): return {"ok": True}\n',
        encoding="utf-8",
    )


def test_full_run_no_llm_smoke(tmp_path: Path):
    _seed_project(tmp_path)
    args = argparse.Namespace(project=str(tmp_path), categories=None, no_llm=True)
    rc = full_run.run(args)
    assert rc == 0

    state = tmp_path / ".qa-agent" / "state"
    for f in (
        "project_map.json",
        "dependency_graph.json",
        "knowledge_graph.json",
        "risk_matrix.json",
        "strategy.json",
        "scenarios.json",
        "generated_tests.json",
        "critique.json",
    ):
        assert (state / f).exists(), f"missing state file: {f}"

    # tests directory created with files for at least api+security
    api_dir = tmp_path / "tests" / "qa-agent" / "api"
    sec_dir = tmp_path / "tests" / "qa-agent" / "security"
    assert any(api_dir.glob("test_*.py"))
    assert any(sec_dir.glob("test_*.py"))


def test_report_command_writes_html(tmp_path: Path):
    _seed_project(tmp_path)
    full_run_args = argparse.Namespace(project=str(tmp_path), categories=None, no_llm=True)
    assert full_run.run(full_run_args) == 0

    report_args = argparse.Namespace(project=str(tmp_path), open_browser=False)
    assert report.run(report_args) == 0
    runs = tmp_path / ".qa-agent" / "runs"
    assert runs.exists()
    html_files = list(runs.glob("*/report.html"))
    assert html_files, "no report.html generated"
    text = html_files[-1].read_text(encoding="utf-8")
    assert "Quality score" in text
    assert "auth" in text or "payments" in text
