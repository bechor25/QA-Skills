"""compute_coverage real-units math."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_skills.analysis import load_analysis
from qa_skills.coverage import compute_coverage


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fastapi():
    return load_analysis(FIXTURES / "python_fastapi_analysis.json")


def test_api_full_coverage_when_all_routes_covered(fastapi):
    outputs = [
        {"path": "tests/api/auth/test_login.py",    "covers": ["POST /api/login"]},
        {"path": "tests/api/auth/test_me.py",       "covers": ["GET /api/me"]},
        {"path": "tests/api/auth/test_register.py", "covers": ["POST /api/register"]},
        {"path": "tests/api/calc/test_quote.py",    "covers": ["POST /api/calc/quote"]},
        {"path": "tests/api/health/test_health.py", "covers": ["GET /api/health"]},
        {"path": "tests/api/users/test_users.py",   "covers": ["GET /api/users", "GET /api/users/{id}"]},
    ]
    cov = compute_coverage("api", outputs, fastapi)
    assert cov["pct"] == 100
    assert cov["total"] == 7
    assert cov["missing_items"] == []


def test_api_partial_coverage_real_units(fastapi):
    """Even though we have 5 of 6 expected_files passing, only 5/7 routes covered."""
    outputs = [
        {"path": "tests/api/auth/test_login.py",    "covers": ["POST /api/login"]},
        {"path": "tests/api/auth/test_me.py",       "covers": ["GET /api/me"]},
        {"path": "tests/api/auth/test_register.py", "covers": ["POST /api/register"]},
        {"path": "tests/api/calc/test_quote.py",    "covers": ["POST /api/calc/quote"]},
        {"path": "tests/api/health/test_health.py", "covers": ["GET /api/health"]},
        # users.py missing entirely (covers /api/users + /api/users/{id})
    ]
    cov = compute_coverage("api", outputs, fastapi)
    assert cov["total"] == 7
    # 5 routes covered, 2 missing
    assert cov["pct"] == int(100 * 5 / 7)
    assert "GET /api/users" in cov["missing_items"]
    assert "GET /api/users/{id}" in cov["missing_items"]


def test_unit_coverage_uses_module_paths(fastapi):
    """Controllers excluded from unit universe (covered by api/ui)."""
    outputs = [
        {"path": "tests/unit/main/test_main.py", "covers": ["app/main.py"]},
        {"path": "tests/unit/auth/test_auth.py", "covers": ["app/auth.py"]},
    ]
    cov = compute_coverage("unit", outputs, fastapi)
    # universe = {main, auth, users, calc} — routes.py (controller) is filtered.
    assert cov["total"] == 4
    assert cov["pct"] == 50   # 2/4
    assert sorted(cov["covered_items"]) == ["app/auth.py", "app/main.py"]
    assert "app/routes.py" not in cov["covered_items"]
    assert "app/routes.py" not in cov["missing_items"]


def test_ui_coverage_uses_page_paths(fastapi):
    outputs = [
        {"path": "tests/ui/index/test_index.py", "covers": ["templates/index.html"]},
    ]
    cov = compute_coverage("ui", outputs, fastapi)
    assert cov["total"] == 3
    assert cov["pct"] == 33   # 1/3 → int truncation
    assert cov["covered_items"] == ["templates/index.html"]
    assert "templates/login.html" in cov["missing_items"]


def test_zero_universe_returns_zero_pct(fastapi):
    """Empty universe MUST not divide-by-zero."""
    cov = compute_coverage("nonexistent", [], fastapi)
    assert cov["pct"] == 0
    assert cov["total"] == 0


def test_phantom_coverage_filtered_out(fastapi):
    """Sub-agent claims to cover a non-existent route → filtered."""
    outputs = [
        {"path": "tests/api/auth/test_login.py",
         "covers": ["POST /api/login", "POST /api/nonexistent"]},
    ]
    cov = compute_coverage("api", outputs, fastapi)
    assert "POST /api/nonexistent" not in cov["covered_items"]
    assert "POST /api/login" in cov["covered_items"]
