"""Dataclasses backing the QA-Skills runtime contract.

All shapes mirror the JSON Schemas under `skills/_shared/schemas/`. Use
`from_dict` to load; use `dataclasses.asdict` to serialize.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

ROUTE_KIND = ("api", "page", "asset", "unknown")
ROUTE_PRODUCES = ("json", "html", "unknown")
MODULE_TYPE = ("service", "controller", "model", "util", "middleware", "frontend")
FRONTEND_KIND = ("spa_component", "ssr_template", "static_html", "page", "partial", "layout")
LANGUAGE = ("typescript", "javascript", "python", "multi")
CATEGORY = ("unit", "api", "ui", "security", "a11y", "contract")


@dataclass(frozen=True)
class Module:
    path: str
    hash: str
    type: str
    exports: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    has_db_queries: bool = False
    has_http_calls: bool = False
    has_auth: bool = False
    input_fields: tuple[str, ...] = ()
    diff_class: str = "unknown"

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        return cls(
            path=d["path"],
            hash=d["hash"],
            type=d["type"],
            exports=tuple(d.get("exports") or ()),
            dependencies=tuple(d.get("dependencies") or ()),
            has_db_queries=bool(d.get("has_db_queries", False)),
            has_http_calls=bool(d.get("has_http_calls", False)),
            has_auth=bool(d.get("has_auth", False)),
            input_fields=tuple(d.get("input_fields") or ()),
            diff_class=d.get("diff_class", "unknown"),
        )


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: str
    file: str
    requires_auth: bool = False
    kind: str = "unknown"
    produces: str = "unknown"
    source: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Route":
        return cls(
            method=d["method"],
            path=d["path"],
            handler=d["handler"],
            file=d["file"],
            requires_auth=bool(d.get("requires_auth", False)),
            kind=d.get("kind", "unknown"),
            produces=d.get("produces", "unknown"),
            source=d.get("source"),
        )

    @property
    def covers_id(self) -> str:
        """Canonical 'METHOD /path' id used in expected_files[].covers."""
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class FrontendFile:
    path: str
    hash: str
    kind: str
    has_forms: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "FrontendFile":
        return cls(
            path=d["path"],
            hash=d["hash"],
            kind=d["kind"],
            has_forms=bool(d.get("has_forms", False)),
        )


@dataclass(frozen=True)
class ServerHint:
    backend_command: str | None = None
    backend_port: int | None = None
    frontend_command: str | None = None
    frontend_port: int | None = None
    framework: str | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "ServerHint | None":
        if not d:
            return None
        return cls(
            backend_command=d.get("backend_command"),
            backend_port=d.get("backend_port"),
            frontend_command=d.get("frontend_command"),
            frontend_port=d.get("frontend_port"),
            framework=d.get("framework"),
        )


@dataclass(frozen=True)
class Analysis:
    language: str
    project_root: str
    scanned_at: str
    modules: tuple[Module, ...]
    routes: tuple[Route, ...]
    frontend_files: tuple[FrontendFile, ...] = ()
    frontend_kind: str = "none"
    frontend_dev_server: str | None = None
    backend_dev_server: str | None = None
    server_hint: ServerHint | None = None
    stats: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    additional_languages: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "Analysis":
        return cls(
            language=d["language"],
            project_root=d["project_root"],
            scanned_at=d["scanned_at"],
            modules=tuple(Module.from_dict(m) for m in d.get("modules") or ()),
            routes=tuple(Route.from_dict(r) for r in d.get("routes") or ()),
            frontend_files=tuple(FrontendFile.from_dict(f) for f in d.get("frontend_files") or ()),
            frontend_kind=d.get("frontend_kind", "none"),
            frontend_dev_server=d.get("frontend_dev_server"),
            backend_dev_server=d.get("backend_dev_server"),
            server_hint=ServerHint.from_dict(d.get("server_hint")),
            stats=d.get("stats") or {},
            warnings=tuple(d.get("warnings") or ()),
            additional_languages=tuple(d.get("additional_languages") or ()),
        )

    def api_routes(self) -> Iterable[Route]:
        # Framework-internal endpoints (FastAPI auto-spec, Swagger UI) are not
        # real product APIs — exclude from test planning + coverage universe.
        skip = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
        return (r for r in self.routes if r.kind == "api" and r.path not in skip)

    def page_routes(self) -> Iterable[Route]:
        return (r for r in self.routes if r.kind == "page")

    def page_files(self) -> Iterable[FrontendFile]:
        page_kinds = {"page", "ssr_template", "spa_component", "static_html"}
        return (f for f in self.frontend_files if f.kind in page_kinds)

    def non_frontend_modules(self) -> Iterable[Module]:
        # Controllers are covered by api/ui categories — a `TestClient`-based
        # "unit" file for a controller duplicates those tests verbatim.
        skip_types = {"frontend", "controller"}
        return (m for m in self.modules if m.type not in skip_types)


@dataclass(frozen=True)
class ExpectedFile:
    path: str
    covers: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"path": self.path, "covers": list(self.covers)}


@dataclass(frozen=True)
class ServerPlan:
    url: str | None
    start_command: str | None
    start_allowed: bool
    timeout_seconds: int = 30
    cleanup_pid: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentResult:
    agent: str
    status: str   # "passed" | "partial" | "error" | "skipped:<reason>"
    outputs: list[dict] = field(default_factory=list)
    tokens_used_estimate: int = 0
    artifacts_dir: str | None = None
    html_report: str | None = None
    findings: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # drop reason/warnings/findings if empty to keep payload small
        if not self.reason:
            d.pop("reason", None)
        return d


__all__ = [
    "ROUTE_KIND",
    "ROUTE_PRODUCES",
    "MODULE_TYPE",
    "FRONTEND_KIND",
    "LANGUAGE",
    "CATEGORY",
    "Module",
    "Route",
    "FrontendFile",
    "ServerHint",
    "Analysis",
    "ExpectedFile",
    "ServerPlan",
    "AgentResult",
]
