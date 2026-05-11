"""server.build_server_plan tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_skills.analysis import load_analysis
from qa_skills.server import build_server_plan, is_reachable


FIXTURES = Path(__file__).parent / "fixtures"


def test_fastapi_plan_uses_backend_command():
    a = load_analysis(FIXTURES / "python_fastapi_analysis.json")
    plan = build_server_plan(a)
    assert plan.url == "http://localhost:8000"
    assert plan.start_command == "uvicorn app.main:app --reload"
    assert plan.start_allowed is False  # default — never auto-start


def test_express_plan_spa_prefers_frontend_command():
    a = load_analysis(FIXTURES / "typescript_express_analysis.json")
    plan = build_server_plan(a)
    assert plan.url == "http://localhost:5173"
    assert plan.start_command == "npm run dev"   # SPA → frontend wins
    assert plan.start_allowed is False


def test_explicit_allow_overrides_default():
    a = load_analysis(FIXTURES / "python_fastapi_analysis.json")
    plan = build_server_plan(a, allow_start_explicit=True)
    assert plan.start_allowed is True


def test_explicit_disallow_overrides_default():
    a = load_analysis(FIXTURES / "python_fastapi_analysis.json")
    plan = build_server_plan(a, allow_start_explicit=False)
    assert plan.start_allowed is False


def test_is_reachable_unreachable_localhost_high_port():
    """Pick a port nothing should be on. Reachability returns False fast."""
    assert is_reachable("http://127.0.0.1:1", timeout=0.5) is False
