"""compute_expected_files acceptance tests.

Adversarial fixtures: Python FastAPI + TS/JS Express. Asserts the planner
produces the exact paths a sub-agent must write.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.analysis import load_analysis
from qa_skills.path_planner import compute_expected_files
from qa_skills.types import Analysis


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Analysis:
    return load_analysis(FIXTURES / name)


@pytest.fixture
def fastapi() -> Analysis:
    return _load("python_fastapi_analysis.json")


@pytest.fixture
def express() -> Analysis:
    return _load("typescript_express_analysis.json")


def _paths(efs):
    return [ef.path for ef in efs]


# ---------- Python FastAPI ----------

def test_unit_python_fastapi(fastapi):
    """Controllers (routes.py) excluded — TestClient `unit` tests for controllers
    duplicate api/ui categories. main.py is a service in this fixture, kept."""
    paths = _paths(compute_expected_files("unit", fastapi, "python"))
    assert paths == [
        "tests/unit/main/test_main.py",
        "tests/unit/auth/test_auth.py",
        "tests/unit/users/test_users.py",
        "tests/unit/calc/test_calc.py",
    ]
    assert "tests/unit/routes/test_routes.py" not in paths


def test_api_python_fastapi(fastapi):
    paths = _paths(compute_expected_files("api", fastapi, "python"))
    assert paths == [
        "tests/api/auth/test_login.py",
        "tests/api/auth/test_me.py",
        "tests/api/auth/test_register.py",
        "tests/api/calc/test_quote.py",
        "tests/api/health/test_health.py",
        "tests/api/users/test_users.py",
    ]


def test_security_python_fastapi(fastapi):
    paths = _paths(compute_expected_files("security", fastapi, "python"))
    assert paths == [
        "tests/security/auth/test_login_security.py",
        "tests/security/auth/test_me_security.py",
        "tests/security/auth/test_register_security.py",
        "tests/security/calc/test_quote_security.py",
        "tests/security/health/test_health_security.py",
        "tests/security/users/test_users_security.py",
    ]


def test_contract_python_fastapi(fastapi):
    paths = _paths(compute_expected_files("contract", fastapi, "python"))
    assert paths == [
        "tests/contract/auth/test_login.py",
        "tests/contract/auth/test_me.py",
        "tests/contract/auth/test_register.py",
        "tests/contract/calc/test_quote.py",
        "tests/contract/health/test_health.py",
        "tests/contract/users/test_users.py",
    ]


def test_ui_python_fastapi(fastapi):
    paths = _paths(compute_expected_files("ui", fastapi, "python"))
    assert paths == [
        "tests/ui/index/test_index.py",
        "tests/ui/login/test_login.py",
        "tests/ui/quote/test_quote.py",
    ]


def test_a11y_python_fastapi(fastapi):
    paths = _paths(compute_expected_files("a11y", fastapi, "python"))
    assert paths == [
        "tests/a11y/index/test_index.py",
        "tests/a11y/login/test_login.py",
        "tests/a11y/quote/test_quote.py",
    ]


def test_users_groups_two_routes(fastapi):
    """GET /api/users + GET /api/users/{id} → ONE file."""
    efs = compute_expected_files("api", fastapi, "python")
    users = next(ef for ef in efs if ef.path == "tests/api/users/test_users.py")
    assert sorted(users.covers) == ["GET /api/users", "GET /api/users/{id}"]


def test_health_separate_from_users(fastapi):
    """/api/health must NOT be grouped under users — common past bug."""
    efs = compute_expected_files("api", fastapi, "python")
    paths = _paths(efs)
    assert "tests/api/health/test_health.py" in paths
    health = next(ef for ef in efs if ef.path == "tests/api/health/test_health.py")
    assert health.covers == ("GET /api/health",)


def test_unit_never_collapses_to_root_root(fastapi):
    """No `tests/unit/root/test_root.py` unless source is truly at project root."""
    paths = _paths(compute_expected_files("unit", fastapi, "python"))
    assert "tests/unit/root/test_root.py" not in paths


# ---------- TS/JS Express ----------

def test_unit_typescript(express):
    """Controllers excluded — see test_unit_python_fastapi for rationale."""
    paths = _paths(compute_expected_files("unit", express, "typescript"))
    assert paths == [
        "tests/unit/auth/login.test.ts",
        "tests/unit/users/manager.test.ts",
    ]
    assert "tests/unit/routes/auth.test.ts" not in paths
    assert "tests/unit/routes/users.test.ts" not in paths


def test_api_typescript(express):
    paths = _paths(compute_expected_files("api", express, "typescript"))
    assert paths == [
        "tests/api/auth/login.api.test.ts",
        "tests/api/auth/register.api.test.ts",
        "tests/api/users/users.api.test.ts",
    ]


def test_ui_typescript(express):
    paths = _paths(compute_expected_files("ui", express, "typescript"))
    assert paths == [
        "tests/ui/Home/Home.spec.ts",
        "tests/ui/Login/Login.spec.ts",
        "tests/ui/Dashboard/Dashboard.spec.ts",
    ]


# ---------- Path regex compliance ----------

from qa_skills.validators import PY_PATH_REGEX, TS_PATH_REGEX


@pytest.mark.parametrize("category", ["unit", "api", "security", "contract", "ui", "a11y"])
def test_all_paths_match_required_pattern_python(fastapi, category):
    for ef in compute_expected_files(category, fastapi, "python"):
        assert PY_PATH_REGEX.match(ef.path), f"{category}: {ef.path}"


@pytest.mark.parametrize("category", ["unit", "api", "security", "contract", "ui", "a11y"])
def test_all_paths_match_required_pattern_typescript(express, category):
    for ef in compute_expected_files(category, express, "typescript"):
        assert TS_PATH_REGEX.match(ef.path), f"{category}: {ef.path}"


# ---------- covers[] semantics ----------

def test_covers_never_empty_or_null(fastapi):
    for cat in ("unit", "api", "security", "contract", "ui", "a11y"):
        for ef in compute_expected_files(cat, fastapi, "python"):
            assert ef.covers, f"{cat}: {ef.path} has empty covers"
            for c in ef.covers:
                assert isinstance(c, str) and c, f"{cat}: {ef.path} covers contains empty/non-string {c!r}"


def test_api_covers_format(fastapi):
    for ef in compute_expected_files("api", fastapi, "python"):
        for c in ef.covers:
            assert " " in c, f"API covers must be 'METHOD /path': {c!r}"
            method, path = c.split(" ", 1)
            assert method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"), c
            assert path.startswith("/"), c


# ---------- framework-internal routes filtered ----------

@pytest.fixture
def fastapi_with_openapi(fastapi):
    """Clone the FastAPI fixture, append framework-internal /openapi.json + /docs."""
    from qa_skills.types import Analysis, Route
    extra = (
        Route(method="GET", path="/openapi.json", handler="", file="app/main.py",
              kind="api", produces="json", source="fastapi"),
        Route(method="GET", path="/docs", handler="", file="app/main.py",
              kind="api", produces="html", source="fastapi"),
        Route(method="GET", path="/redoc", handler="", file="app/main.py",
              kind="api", produces="html", source="fastapi"),
    )
    return Analysis(
        language=fastapi.language,
        project_root=fastapi.project_root,
        scanned_at=fastapi.scanned_at,
        modules=fastapi.modules,
        routes=fastapi.routes + extra,
        frontend_files=fastapi.frontend_files,
        frontend_kind=fastapi.frontend_kind,
        frontend_dev_server=fastapi.frontend_dev_server,
        backend_dev_server=fastapi.backend_dev_server,
        server_hint=fastapi.server_hint,
        stats=fastapi.stats,
        warnings=fastapi.warnings,
    )


@pytest.mark.parametrize("category", ["api", "security", "contract"])
def test_framework_internal_routes_filtered(fastapi_with_openapi, category):
    """/openapi.json /docs /redoc must NEVER appear in expected_files —
    FastAPI auto-generates them, not real product APIs."""
    paths = _paths(compute_expected_files(category, fastapi_with_openapi, "python"))
    forbidden = ("openapi.json", "docs", "redoc")
    for p in paths:
        for f in forbidden:
            assert f"/{f}/" not in p, f"{category}: framework-internal route leaked into {p}"


def test_api_routes_iter_excludes_openapi(fastapi_with_openapi):
    api_paths = {r.path for r in fastapi_with_openapi.api_routes()}
    assert "/openapi.json" not in api_paths
    assert "/docs" not in api_paths
    assert "/redoc" not in api_paths
    assert "/api/login" in api_paths   # still kept
