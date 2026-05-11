"""routes.derive_domain_and_tag + is_api_route tests."""

from __future__ import annotations

import pytest

from qa_skills.routes import AUTH_TOPICS, derive_domain_and_tag, is_api_route
from qa_skills.types import Route


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/login",            ("auth", "login")),
        ("/api/register",         ("auth", "register")),
        ("/api/me",               ("auth", "me")),
        ("/api/users",            ("users", "users")),
        ("/api/users/{id}",       ("users", "users")),
        ("/api/calc/quote",       ("calc", "quote")),
        ("/api/health",           ("health", "health")),
        ("/",                     ("root", "index")),
        ("/auth/refresh",         ("auth", "refresh")),
        ("/payments/charge",      ("payments", "charge")),
    ],
)
def test_derive_domain_and_tag(path, expected):
    assert derive_domain_and_tag(path) == expected


def test_auth_topics_complete():
    """Verify the auth-topic set still contains the expected verbs."""
    expected = {"login", "register", "logout", "refresh", "me", "reset",
                "verify", "forgot", "signup", "signin"}
    assert AUTH_TOPICS == expected


def test_is_api_route_kind_authoritative():
    api = Route(method="GET", path="/api/x", handler="h", file="f.py", kind="api")
    page = Route(method="GET", path="/x",   handler="h", file="f.py", kind="page")
    asset = Route(method="GET", path="/s.css", handler="-", file="-", kind="asset")
    assert is_api_route(api) is True
    assert is_api_route(page) is False
    assert is_api_route(asset) is False


def test_is_api_route_unknown_returns_false():
    """Unknown should not be guessed as api — orchestrator should warn separately."""
    r = Route(method="POST", path="/api/foo", handler="h", file="f.py", kind="unknown")
    assert is_api_route(r) is False
