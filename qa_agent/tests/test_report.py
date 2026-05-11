"""Report builder + renderer tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from qa_agent.report.builder import build_report_data
from qa_agent.report.renderer import render_html
from qa_agent.runtime.workspace import new_workspace
from qa_agent.state import schemas
from qa_agent.state.manager import StateManager


def _seed(tmp_path: Path) -> None:
    sm = StateManager(tmp_path)
    now = datetime.now(timezone.utc)
    sm.save(
        schemas.ProjectMap(
            project_root=str(tmp_path),
            scanned_at=now,
            languages={"python": 5},
            frameworks=[
                schemas.FrameworkEntry(name="FastAPI", language="python", confidence=0.9, evidence=["py:fastapi"])
            ],
            package_managers=["pip"],
        )
    )
    sm.save(schemas.KnowledgeGraph(built_at=now, project_summary="demo"))
    sm.save(
        schemas.RiskMatrix(
            built_at=now,
            entries=[
                schemas.RiskEntry(
                    capability="auth",
                    feature_id="feat::auth",
                    business_impact=5,
                    state_complexity=3,
                    security_exposure=5,
                    change_frequency=2,
                    score=30.0,
                    rationale="auth: high",
                )
            ],
        )
    )
    sm.save(
        schemas.Strategy(
            built_at=now,
            entries=[
                schemas.StrategyEntry(
                    capability="auth",
                    feature_id="feat::auth",
                    categories=["api", "security"],
                    priority=10,
                    rationale="t",
                )
            ],
        )
    )
    sm.save(
        schemas.ExecutionHistory(
            records=[
                schemas.ExecutionRecord(
                    run_id="r1",
                    started_at=now,
                    finished_at=now,
                    category="api",
                    test_files=["a.py"],
                    passed=3,
                    failed=1,
                    skipped=0,
                    duration_seconds=1.0,
                    exit_code=1,
                )
            ]
        )
    )


def test_report_builder_emits_expected_keys(tmp_path: Path):
    _seed(tmp_path)
    data = build_report_data(str(tmp_path))
    assert set(data.keys()) >= {
        "executive_summary", "risk", "strategy", "coverage", "tests",
        "scenarios", "critique", "flaky", "installations", "executions", "project",
    }
    assert data["executive_summary"]["tests_total"] == 4
    assert data["executive_summary"]["passed"] == 3
    assert data["executive_summary"]["failed"] == 1
    assert data["executive_summary"]["quality_score"] > 0


def test_quality_score_drops_with_flaky(tmp_path: Path):
    _seed(tmp_path)
    sm = StateManager(tmp_path)
    sm.save(
        schemas.FlakyState(
            entries=[
                schemas.FlakyEntry(
                    test_id="a.py",
                    classification="timing",
                    runs=3,
                    failures=2,
                    last_seen=datetime.now(timezone.utc),
                    rationale="t",
                )
            ]
        )
    )
    data = build_report_data(str(tmp_path))
    assert data["executive_summary"]["flaky"] == 1


def test_render_html_writes_file(tmp_path: Path):
    _seed(tmp_path)
    ws = new_workspace(tmp_path)
    data = build_report_data(str(tmp_path))
    html_path = render_html(data, str(tmp_path), ws.run_id)
    assert html_path.exists()
    text = html_path.read_text(encoding="utf-8")
    assert "QA Agent" in text
    assert "Quality score" in text
    assert "auth" in text
