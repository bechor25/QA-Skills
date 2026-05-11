"""gaps module tests."""

from __future__ import annotations

from qa_skills.gaps import classify_module_gap, classify_route_gap, identify_gaps
from qa_skills.types import Module, Route


def _module(**kwargs) -> Module:
    defaults = {
        "path": "app/x.py", "hash": "h", "type": "service",
        "exports": (), "dependencies": (), "has_db_queries": False,
        "has_http_calls": False, "has_auth": False, "input_fields": (),
    }
    defaults.update(kwargs)
    return Module(**defaults)


def test_high_severity_when_auth_no_security_tests():
    m = _module(path="app/auth.py", has_auth=True)
    g = classify_module_gap(m, has_unit_tests=True, has_security_tests=False)
    assert g["severity"] == "high"


def test_high_severity_when_payments_uncovered():
    m = _module(path="app/payments/charge.py")
    g = classify_module_gap(m, has_unit_tests=False, has_security_tests=False)
    assert g["severity"] == "high"
    assert "payments" in g["reason"]


def test_medium_severity_when_db_queries_uncovered():
    m = _module(path="app/users.py", has_db_queries=True)
    g = classify_module_gap(m, has_unit_tests=False, has_security_tests=False)
    assert g["severity"] == "medium"


def test_medium_severity_when_input_fields_uncovered():
    m = _module(path="app/contact.py", input_fields=("email",))
    g = classify_module_gap(m, has_unit_tests=False, has_security_tests=False)
    assert g["severity"] == "medium"


def test_low_severity_plain_uncovered():
    m = _module(path="app/util.py")
    g = classify_module_gap(m, has_unit_tests=False, has_security_tests=False)
    assert g["severity"] == "low"


def test_no_gap_when_covered_and_safe():
    m = _module(path="app/util.py")
    g = classify_module_gap(m, has_unit_tests=True, has_security_tests=False)
    assert g is None


def test_route_high_when_unauth_db_no_tests():
    r = Route(method="POST", path="/api/users", handler="h", file="app/users.py", requires_auth=False, kind="api")
    g = classify_route_gap(r, has_api_tests=False, module_has_db_queries=True)
    assert g["severity"] == "high"


def test_route_no_gap_when_covered():
    r = Route(method="GET", path="/api/users", handler="h", file="app/users.py", requires_auth=True, kind="api")
    g = classify_route_gap(r, has_api_tests=True, module_has_db_queries=True)
    assert g is None


def test_identify_gaps_sorted_by_severity():
    modules = [
        _module(path="app/util.py"),
        _module(path="app/auth.py", has_auth=True),
        _module(path="app/users.py", has_db_queries=True),
    ]
    gaps = identify_gaps(modules, [], covered_modules=set(), covered_routes=set(), secured_modules=set())
    severities = [g["severity"] for g in gaps]
    assert severities == sorted(severities, key={"high":0,"medium":1,"low":2}.get)
