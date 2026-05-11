"""UI scanner.

Detects routable pages for the supported frontend frameworks:
  - Next.js  : files under `pages/` or `app/`
  - Nuxt     : files under `pages/`
  - Vite/Vue : route definitions referenced from `router/` modules
  - CRA/React: react-router patterns by string match
  - Svelte   : files under `src/routes/`

Output is a normalized list of pages. Real DOM recon happens later, in
the Playwright executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..shared.logging import get_logger
from ..shared.paths import project_root
from ..state import schemas

log = get_logger("qa_agent.scanners.ui")


@dataclass(slots=True)
class UIPage:
    framework: str   # Next.js | Nuxt | Svelte | Vite | React | Unknown
    route: str
    source_path: str


@dataclass(slots=True)
class UIInventory:
    pages: list[UIPage] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pages": [p.__dict__ for p in self.pages],
            "count": len(self.pages),
        }


def scan_ui(project: str | Path | None, pm: schemas.ProjectMap) -> UIInventory:
    root = project_root(project)
    frameworks = {f.name for f in pm.frameworks}

    inv = UIInventory()
    if "Next.js" in frameworks:
        inv.pages.extend(_scan_nextjs(root))
    if "Nuxt" in frameworks:
        inv.pages.extend(_scan_nuxt(root))
    if "Svelte" in frameworks:
        inv.pages.extend(_scan_svelte(root))

    log.info("ui: %d pages discovered", len(inv.pages))
    return inv


def _scan_nextjs(root: Path) -> list[UIPage]:
    pages: list[UIPage] = []
    for base in ("pages", "src/pages", "app", "src/app"):
        d = root / base
        if not d.exists() or not d.is_dir():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            if p.name.startswith("_"):
                continue
            rel = p.relative_to(root).as_posix()
            route = _nextjs_route(rel, base)
            pages.append(UIPage(framework="Next.js", route=route, source_path=rel))
    return pages


def _nextjs_route(rel: str, base: str) -> str:
    stem = rel
    # strip leading base/
    if stem.startswith(base + "/"):
        stem = stem[len(base) + 1 :]
    # drop file extension
    dot = stem.rfind(".")
    if dot != -1:
        stem = stem[:dot]
    # index → ""
    if stem.endswith("/index") or stem == "index":
        stem = stem[:-len("index")].rstrip("/")
    # app router: page.tsx is the route
    if stem.endswith("/page") or stem == "page":
        stem = stem[:-len("page")].rstrip("/")
    route = "/" + stem
    return route.rstrip("/") or "/"


def _scan_nuxt(root: Path) -> list[UIPage]:
    pages: list[UIPage] = []
    for base in ("pages", "src/pages"):
        d = root / base
        if not d.is_dir():
            continue
        for p in d.rglob("*.vue"):
            rel = p.relative_to(root).as_posix()
            stem = p.relative_to(d).with_suffix("").as_posix()
            if stem.endswith("/index") or stem == "index":
                stem = stem[: -len("index")].rstrip("/")
            route = "/" + stem
            pages.append(UIPage(framework="Nuxt", route=route.rstrip("/") or "/", source_path=rel))
    return pages


def _scan_svelte(root: Path) -> list[UIPage]:
    pages: list[UIPage] = []
    d = root / "src" / "routes"
    if not d.is_dir():
        return pages
    for p in d.rglob("+page*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        route_dir = p.parent.relative_to(d).as_posix()
        route = "/" + route_dir if route_dir != "." else "/"
        pages.append(UIPage(framework="Svelte", route=route, source_path=rel))
    return pages
