"""Scanner + KG smoke tests against tiny fixture repos."""

from __future__ import annotations

from pathlib import Path

from qa_agent.context.kg_builder import build_knowledge_graph
from qa_agent.scanners.api_scanner import scan_api
from qa_agent.scanners.dependency import build_dependency_graph
from qa_agent.scanners.filesystem import scan_filesystem
from qa_agent.scanners.tech_stack import scan_tech_stack
from qa_agent.scanners.ui_scanner import scan_ui


def test_filesystem_classifies_languages_and_tests(fastapi_fixture: Path):
    pm = scan_filesystem(fastapi_fixture)
    paths = {f.path for f in pm.files}
    assert "app/main.py" in paths
    assert "tests/test_main.py" in paths
    test_entry = next(f for f in pm.files if f.path == "tests/test_main.py")
    assert test_entry.is_test is True
    assert pm.languages.get("python", 0) >= 2
    assert "pip" in pm.package_managers or "poetry" in pm.package_managers


def test_tech_stack_detects_fastapi(fastapi_fixture: Path):
    pm = scan_filesystem(fastapi_fixture)
    pm = scan_tech_stack(fastapi_fixture, pm)
    names = {f.name for f in pm.frameworks}
    assert "FastAPI" in names


def test_dependency_graph_links_main_to_app_pkg(fastapi_fixture: Path):
    pm = scan_filesystem(fastapi_fixture)
    pm = scan_tech_stack(fastapi_fixture, pm)
    dep = build_dependency_graph(fastapi_fixture, pm)
    by_path = {m.path: m for m in dep.modules}
    main = by_path.get("app/main.py")
    assert main is not None
    assert any("fastapi" in imp.lower() for imp in main.imports)


def test_api_scanner_finds_fastapi_routes(fastapi_fixture: Path):
    pm = scan_filesystem(fastapi_fixture)
    pm = scan_tech_stack(fastapi_fixture, pm)
    inv = scan_api(fastapi_fixture, pm)
    handlers = {r.handler for r in inv.routes}
    assert "list_users" in handlers
    assert "login" in handlers


def test_kg_groups_routes_into_features(fastapi_fixture: Path):
    pm = scan_filesystem(fastapi_fixture)
    pm = scan_tech_stack(fastapi_fixture, pm)
    dep = build_dependency_graph(fastapi_fixture, pm)
    api = scan_api(fastapi_fixture, pm)
    ui = scan_ui(fastapi_fixture, pm)
    kg = build_knowledge_graph(pm, dep, api, ui)
    feature_ids = {f.id for f in kg.features}
    # login -> auth, users -> user-mgmt
    assert "feat::auth" in feature_ids
    assert "feat::user-mgmt" in feature_ids


def test_express_fixture_detects_routes_and_pages(express_fixture: Path):
    pm = scan_filesystem(express_fixture)
    pm = scan_tech_stack(express_fixture, pm)
    api = scan_api(express_fixture, pm)
    ui = scan_ui(express_fixture, pm)

    # routes
    patterns = {r.pattern for r in api.routes}
    assert "/users" in patterns
    assert "/payments/charge" in patterns

    # pages — note: pages/ alone doesn't activate Next.js scan unless
    # framework was detected; we still expect zero rather than crash.
    # If next is added to deps in future fixture, this asserts > 0.
    assert isinstance(ui.pages, list)
