"""API scanner.

Pulls route definitions out of parsed files (python_ast already flags
FastAPI/Flask/DRF; ts_morph_bridge flags Express/Koa/Fastify-style chains).
Output is a normalized list of routes keyed by module path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..parsers.python_ast import parse_python_file
from ..parsers.ts_morph_bridge import parse_ts_files
from ..parsers.types import ParsedFile
from ..shared.logging import get_logger
from ..shared.paths import project_root
from ..state import schemas

log = get_logger("qa_agent.scanners.api")


@dataclass(slots=True)
class RouteEntry:
    """Normalized API route emitted by the scanner."""

    module_path: str
    method: str          # GET | POST | ... | ROUTE | DECORATOR
    pattern: str         # raw path or decorator name
    handler: str         # function/method name
    framework: str       # FastAPI | Flask | Express | DRF | Unknown
    line: int | None = None


@dataclass(slots=True)
class ApiInventory:
    routes: list[RouteEntry] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "routes": [r.__dict__ for r in self.routes],
            "count": len(self.routes),
        }


def scan_api(project: str | Path | None, pm: schemas.ProjectMap) -> ApiInventory:
    """Walk parseable files, extract route entries."""
    root = project_root(project)
    inv = ApiInventory()

    py_files = [f.path for f in pm.files if f.language == "python" and not f.is_test]
    ts_files = [
        f.path
        for f in pm.files
        if f.language in {"typescript", "javascript"} and not f.is_test
    ]

    for rel in py_files:
        pf = parse_python_file(root, rel)
        inv.routes.extend(_routes_from_python(pf))

    if ts_files:
        for pf in parse_ts_files(root, ts_files):
            inv.routes.extend(_routes_from_ts(pf))

    log.info("api: discovered %d routes", len(inv.routes))
    return inv


def _routes_from_python(pf: ParsedFile) -> list[RouteEntry]:
    if pf.parse_error:
        return []
    out: list[RouteEntry] = []
    for sym in pf.routes:
        framework = _python_framework_for(sym.decorators)
        method, pattern = _extract_python_route(sym)
        out.append(
            RouteEntry(
                module_path=pf.path,
                method=method,
                pattern=pattern,
                handler=sym.name,
                framework=framework,
                line=sym.line,
            )
        )
    return out


def _python_framework_for(decorators: list[str]) -> str:
    flat = " ".join(decorators).lower()
    if "fastapi" in flat or "apirouter" in flat:
        return "FastAPI"
    if "flask" in flat or "blueprint" in flat or "quart" in flat:
        return "Flask"
    if "api_view" in flat or "rest_framework" in flat:
        return "DRF"
    return "Unknown"


def _extract_python_route(sym) -> tuple[str, str]:
    """Best-effort extraction. Real route pattern lives in the decorator
    call (which python_ast keeps only as a name string). For now use the
    decorator's last attribute (e.g. `get`) as the method and an empty
    pattern — Phase 2 will re-parse decorator args via ast.Call for
    better fidelity.
    """
    for deco in sym.decorators:
        last = deco.rsplit(".", 1)[-1].upper()
        return last, ""
    return "ROUTE", ""


def _routes_from_ts(pf: ParsedFile) -> list[RouteEntry]:
    if pf.parse_error:
        return []
    out: list[RouteEntry] = []
    for sym in pf.routes:
        method, pattern = _split_ts_route_name(sym.name)
        out.append(
            RouteEntry(
                module_path=pf.path,
                method=method,
                pattern=pattern,
                handler="<inline>",
                framework="Express",
                line=sym.line,
            )
        )
    return out


def _split_ts_route_name(raw: str) -> tuple[str, str]:
    # The node helper emits "GET /users" style names.
    parts = raw.split(" ", 1)
    if len(parts) == 2:
        return parts[0].upper(), parts[1]
    return "GET", raw
