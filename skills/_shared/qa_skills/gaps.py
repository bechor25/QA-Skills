"""Gap identification — deterministic severity classification.

Replaces inline rules in qa-coverage-reporter.md Phase 3. Pure function — no IO.
"""

from __future__ import annotations

from typing import Iterable

from .types import Module, Route

HIGH_RISK_PATH_PARTS = ("payments", "billing", "charge", "checkout", "money", "wallet")


def _path_in_high_risk(path: str) -> bool:
    p = path.lower()
    return any(seg in p for seg in HIGH_RISK_PATH_PARTS)


def classify_module_gap(
    module: Module,
    *,
    has_unit_tests: bool,
    has_security_tests: bool,
) -> dict | None:
    """Return a gap dict for an uncovered/under-tested module, or None when adequate.

    Severity rules (mirror reference/category-boundaries.md):
    - high:   has_auth + no security tests, OR high-risk path uncovered
    - medium: has_db_queries + uncovered, OR has input_fields + uncovered
    - low:    plain uncovered
    """
    uncovered = not has_unit_tests
    if module.has_auth and not has_security_tests:
        return {"path": module.path, "severity": "high",
                "reason": "module touches auth but has no security tests"}
    if uncovered and _path_in_high_risk(module.path):
        return {"path": module.path, "severity": "high",
                "reason": "uncovered module in payments/money path"}
    if uncovered and module.has_db_queries:
        return {"path": module.path, "severity": "medium",
                "reason": "uncovered module makes DB queries"}
    if uncovered and module.input_fields:
        return {"path": module.path, "severity": "medium",
                "reason": "uncovered module has input fields"}
    if uncovered:
        return {"path": module.path, "severity": "low",
                "reason": "uncovered module"}
    return None


def classify_route_gap(
    route: Route,
    *,
    has_api_tests: bool,
    module_has_db_queries: bool,
) -> dict | None:
    """Gap rules for routes.
    - high: unauthenticated + DB-touching + no API tests
    - low:  unauthenticated + no API tests
    """
    if has_api_tests:
        return None
    if not route.requires_auth and module_has_db_queries:
        return {"path": route.covers_id, "severity": "high",
                "reason": "unauthenticated route touches DB without API tests"}
    if not has_api_tests:
        return {"path": route.covers_id, "severity": "low",
                "reason": "route has no API tests"}
    return None


def identify_gaps(
    modules: Iterable[Module],
    routes: Iterable[Route],
    covered_modules: set[str],
    covered_routes: set[str],
    secured_modules: set[str],
) -> list[dict]:
    """Run both module and route classifiers. Returns list sorted by severity."""
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    out: list[dict] = []

    for m in modules:
        if m.type == "frontend":
            continue
        gap = classify_module_gap(
            m,
            has_unit_tests=m.path in covered_modules,
            has_security_tests=m.path in secured_modules,
        )
        if gap:
            out.append(gap)

    routes = list(routes)
    module_db_lookup = {}
    for m in modules:
        module_db_lookup[m.path] = m.has_db_queries

    for r in routes:
        gap = classify_route_gap(
            r,
            has_api_tests=r.covers_id in covered_routes,
            module_has_db_queries=module_db_lookup.get(r.file, False),
        )
        if gap:
            out.append(gap)

    out.sort(key=lambda g: (severity_rank.get(g["severity"], 9), g["path"]))
    return out


__all__ = ["classify_module_gap", "classify_route_gap", "identify_gaps", "HIGH_RISK_PATH_PARTS"]
