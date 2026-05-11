"""Scenario + generator + critic tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from qa_agent.quality.assertion_validator import validate_test_file
from qa_agent.quality.generation_loop import run_generation_loop
from qa_agent.quality.scenario_generator import (
    build_baseline_scenarios,
    validate_llm_scenarios,
)
from qa_agent.quality.test_critic import critique_files
from qa_agent.shared.errors import StrategyError
from qa_agent.state import schemas


def _strategy(*entries: tuple[str, list[str]]) -> schemas.Strategy:
    items = [
        schemas.StrategyEntry(
            capability=c,
            feature_id=f"feat::{c}",
            categories=cats,
            priority=7,
            rationale="t",
        )
        for c, cats in entries
    ]
    return schemas.Strategy(built_at=datetime.now(timezone.utc), entries=items)


def test_baseline_scenarios_cover_every_category():
    strat = _strategy(("auth", ["api", "ui", "security"]))
    scs = build_baseline_scenarios(strat)
    cats = {s.category for s in scs.entries}
    assert cats == {"api", "ui", "security"}


def test_llm_scenario_validator_rejects_unknown_capability():
    strat = _strategy(("auth", ["api"]))
    with pytest.raises(StrategyError):
        validate_llm_scenarios(
            {
                "entries": [
                    {
                        "capability": "ghost",
                        "category": "api",
                        "steps": [
                            {"keyword": "given", "text": "x"},
                            {"keyword": "when", "text": "y"},
                            {"keyword": "then", "text": "z"},
                        ],
                    }
                ]
            },
            strat,
        )


def test_llm_scenario_validator_rejects_disallowed_category():
    strat = _strategy(("auth", ["api"]))
    with pytest.raises(StrategyError):
        validate_llm_scenarios(
            {
                "entries": [
                    {
                        "capability": "auth",
                        "category": "ui",  # not in strategy
                        "steps": [
                            {"keyword": "given", "text": "x"},
                            {"keyword": "when", "text": "y"},
                            {"keyword": "then", "text": "z"},
                        ],
                    }
                ]
            },
            strat,
        )


def test_generation_loop_writes_files_and_critique(tmp_path: Path):
    strat = _strategy(("auth", ["api", "ui", "security"]))
    scs = build_baseline_scenarios(strat)
    pm = schemas.ProjectMap(
        project_root=str(tmp_path),
        scanned_at=datetime.now(timezone.utc),
        languages={"python": 5},
    )
    generated, critique = run_generation_loop(tmp_path, scs, pm)
    assert len(generated.entries) > 0
    for entry in generated.entries:
        assert (tmp_path / entry.path).exists()
    assert all(r.score >= 7.0 for r in critique.results), "baseline tests should pass critic"


def test_assertion_validator_flags_vacuous_python(tmp_path: Path):
    p = tmp_path / "t.py"
    p.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    findings = validate_test_file(p)
    assert any(f.rule == "python-assert-true" and f.severity == "error" for f in findings)


def test_assertion_validator_flags_vacuous_js(tmp_path: Path):
    p = tmp_path / "t.js"
    p.write_text("test('x', () => { expect(true).toBe(true); });\n", encoding="utf-8")
    findings = validate_test_file(p)
    assert any(f.rule == "vacuous-expect-true" and f.severity == "error" for f in findings)
