"""has_signal tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_skills.analysis import load_analysis
from qa_skills.strategy import has_signal


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fastapi():
    return load_analysis(FIXTURES / "python_fastapi_analysis.json")


@pytest.fixture
def express():
    return load_analysis(FIXTURES / "typescript_express_analysis.json")


@pytest.mark.parametrize("category", ["unit", "api", "contract", "security", "ui", "a11y"])
def test_fastapi_has_signal_for_all_categories(fastapi, category):
    ok, _ = has_signal(category, fastapi)
    assert ok, f"FastAPI sample should activate {category}"


@pytest.mark.parametrize("category", ["unit", "api", "contract", "security", "ui", "a11y"])
def test_express_has_signal_for_all_categories(express, category):
    ok, _ = has_signal(category, express)
    assert ok, f"Express sample should activate {category}"


def test_unknown_category_returns_false(fastapi):
    ok, reason = has_signal("perf", fastapi)
    assert ok is False
    assert reason.startswith("unknown_category:")


def test_security_signal_requires_auth_or_db_or_input(fastapi):
    """FastAPI sample has has_auth modules → security activates."""
    ok, _ = has_signal("security", fastapi)
    assert ok
