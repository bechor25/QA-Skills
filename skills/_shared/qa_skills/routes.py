"""Route helpers — domain/tag derivation, api-route classification."""

from __future__ import annotations

from .types import Route

AUTH_TOPICS: frozenset[str] = frozenset({
    "login", "register", "logout", "refresh", "me", "reset",
    "verify", "forgot", "signup", "signin",
})


def derive_domain_and_tag(route_path: str) -> tuple[str, str]:
    """Split a route path into (domain, tag) for test-file grouping.

    >>> derive_domain_and_tag("/api/login")
    ('auth', 'login')
    >>> derive_domain_and_tag("/api/users")
    ('users', 'users')
    >>> derive_domain_and_tag("/api/users/{id}")
    ('users', 'users')
    >>> derive_domain_and_tag("/api/calc/quote")
    ('calc', 'quote')
    >>> derive_domain_and_tag("/")
    ('root', 'index')
    """
    p = route_path.lstrip("/")
    if p.startswith("api/"):
        p = p[4:]
    parts = [s for s in p.split("/") if s and not s.startswith("{")]
    if not parts:
        return ("root", "index")
    if parts[0] in AUTH_TOPICS:
        return ("auth", parts[0])
    if len(parts) == 1:
        return (parts[0], parts[0])
    return (parts[0], parts[1])


def is_api_route(route: Route) -> bool:
    """Authoritative api-route check: trust the analyzer's `kind` field."""
    return route.kind == "api"


__all__ = ["AUTH_TOPICS", "derive_domain_and_tag", "is_api_route"]
