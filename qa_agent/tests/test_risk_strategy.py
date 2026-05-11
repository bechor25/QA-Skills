"""Risk engine + strategy builder unit tests."""

from __future__ import annotations

import pytest

from qa_agent.quality.risk_engine import build_risk_matrix
from qa_agent.quality.strategy_builder import (
    ALLOWED_CATEGORIES,
    build_baseline_strategy,
    validate_llm_strategy,
)
from qa_agent.shared.errors import StrategyError
from qa_agent.state import schemas
from datetime import datetime, timezone


def _make_kg(features: list[tuple[str, str, int]]) -> schemas.KnowledgeGraph:
    """Build a tiny KG; tuples are (capability, feature_id_suffix, n_symbols)."""
    feats = []
    for cap, suffix, n in features:
        feats.append(
            schemas.FeatureEntry(
                id=f"feat::{cap}{suffix}",
                name=cap.title(),
                summary="",
                module_ids=["src"],
                symbols=[
                    schemas.SymbolEntry(name=f"r{i}", kind="route", path="src/x.py")
                    for i in range(n)
                ],
                capabilities=[cap],
            )
        )
    return schemas.KnowledgeGraph(
        built_at=datetime.now(timezone.utc),
        project_summary="",
        modules=[],
        features=feats,
    )


def test_risk_orders_auth_and_payments_first():
    kg = _make_kg([("auth", "", 4), ("search", "", 4), ("payments", "", 2)])
    rm = build_risk_matrix(None, kg)
    caps = [e.capability for e in rm.entries]
    assert caps[0] in {"auth", "payments"}
    assert "search" in caps


def test_baseline_strategy_only_uses_allowed_categories():
    kg = _make_kg([("auth", "", 4), ("payments", "", 6)])
    rm = build_risk_matrix(None, kg)
    strat = build_baseline_strategy(rm)
    for entry in strat.entries:
        assert set(entry.categories).issubset(ALLOWED_CATEGORIES)


def test_baseline_strategy_priority_correlates_with_score():
    kg = _make_kg([("auth", "", 4), ("search", "", 1)])
    rm = build_risk_matrix(None, kg)
    strat = build_baseline_strategy(rm)
    by_cap = {s.capability: s.priority for s in strat.entries}
    assert by_cap["auth"] > by_cap["search"]


def test_llm_validator_rejects_invented_capability():
    rm = schemas.RiskMatrix(built_at=datetime.now(timezone.utc), entries=[])
    with pytest.raises(StrategyError):
        validate_llm_strategy(
            {"entries": [{"capability": "ghost", "categories": ["api"], "priority": 5}]},
            rm,
        )


def test_llm_validator_rejects_bad_category():
    kg = _make_kg([("auth", "", 1)])
    rm = build_risk_matrix(None, kg)
    with pytest.raises(StrategyError):
        validate_llm_strategy(
            {"entries": [{"capability": "auth", "categories": ["pizza"], "priority": 5}]},
            rm,
        )


def test_llm_validator_accepts_clean_payload():
    kg = _make_kg([("auth", "", 1)])
    rm = build_risk_matrix(None, kg)
    payload = {
        "entries": [
            {
                "capability": "auth",
                "feature_id": "feat::auth",
                "categories": ["api", "security"],
                "priority": 9,
                "rationale": "ok",
            }
        ]
    }
    strat = validate_llm_strategy(payload, rm)
    assert strat.entries[0].priority == 9
    assert strat.entries[0].categories == ["api", "security"]
