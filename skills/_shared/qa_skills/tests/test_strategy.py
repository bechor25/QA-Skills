"""has_signal tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from qa_skills.analysis import load_analysis
from qa_skills.strategy import decide_category, has_signal
from qa_skills.types import ServerPlan


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


# ---------- A3: decide_category server matrix ----------


def _plan(url=None, start_command=None, start_allowed=False):
    return ServerPlan(
        url=url,
        start_command=start_command,
        start_allowed=start_allowed,
        timeout_seconds=30,
        cleanup_pid=None,
    )


@pytest.mark.parametrize("category", ["ui", "a11y"])
def test_decide_category_skips_when_no_server_plan(fastapi, category):
    """No plan → no permission. Skip with no_start_permission."""
    ok, reason = decide_category(category, fastapi, server_plan=None, reachable=False)
    assert ok is False
    assert reason == "server_unreachable_no_start_permission"


@pytest.mark.parametrize("category", ["ui", "a11y"])
def test_decide_category_skips_when_start_disallowed(fastapi, category):
    plan = _plan(url="http://localhost:5173", start_command="npm run dev", start_allowed=False)
    ok, reason = decide_category(category, fastapi, server_plan=plan, reachable=False)
    assert ok is False
    assert reason == "server_unreachable_no_start_permission"


@pytest.mark.parametrize("category", ["ui", "a11y"])
def test_decide_category_skips_when_no_start_command(fastapi, category):
    plan = _plan(url="http://localhost:5173", start_command=None, start_allowed=True)
    ok, reason = decide_category(category, fastapi, server_plan=plan, reachable=False)
    assert ok is False
    assert reason == "server_unreachable_no_start_command"


@pytest.mark.parametrize("category", ["ui", "a11y"])
def test_decide_category_runs_when_reachable(fastapi, category):
    plan = _plan(url="http://localhost:5173", start_command=None, start_allowed=False)
    ok, reason = decide_category(category, fastapi, server_plan=plan, reachable=True)
    assert ok is True
    assert reason == ""


@pytest.mark.parametrize("category", ["ui", "a11y"])
def test_decide_category_runs_when_start_allowed_and_command_set(fastapi, category):
    plan = _plan(url="http://localhost:5173", start_command="npm run dev", start_allowed=True)
    ok, reason = decide_category(category, fastapi, server_plan=plan, reachable=False)
    assert ok is True
    assert reason == ""


def test_decide_category_non_server_gated_ignores_server(fastapi):
    """unit/api/security/contract: server matrix not applied — same as has_signal."""
    for cat in ("unit", "api", "security", "contract"):
        ok, _ = decide_category(cat, fastapi, server_plan=None, reachable=False)
        assert ok is True, f"{cat} should ignore server gate"


def test_decide_category_propagates_no_signal_reason(fastapi):
    """When has_signal returns False, decide_category passes through that reason."""
    ok, reason = decide_category("perf", fastapi, server_plan=None, reachable=False)
    assert ok is False
    assert reason.startswith("unknown_category:")
