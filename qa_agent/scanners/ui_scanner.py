"""UI scanner.

Detects routable pages for the supported frontend frameworks:
  - Next.js  : files under `pages/` or `app/`
  - Nuxt     : files under `pages/`
  - Svelte   : files under `src/routes/`
  - React + react-router-dom : `<Route path="…" element={<X />}/>` parse
  - Vue + vue-router         : `path: '…', component: X` parse
  - generic fallback (deps-gated) : scan ``pages/`` / ``views/`` /
    ``routes/`` directories anywhere in the repo

The router-config parse is the source of truth — the filesystem
fallback only kicks in when the dependency declarations say a router
is present but no parseable router config was found.

Output is a normalized list of pages. Real DOM recon happens later, in
the Playwright executor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..shared.logging import get_logger
from ..shared.paths import project_root
from ..state import schemas
from .tech_stack import _read_npm_deps

log = get_logger("qa_agent.scanners.ui")


@dataclass(slots=True)
class UIPage:
    framework: str   # Next.js | Nuxt | Svelte | React | Vue | Unknown
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


_GENERIC_PAGE_DIR_NAMES = {"pages", "views", "routes", "screens"}
_GENERIC_PAGE_EXTS = {".tsx", ".jsx", ".vue", ".svelte"}
_IGNORE_DIR_NAMES = {
    "node_modules", ".git", ".next", ".nuxt", "dist", "build",
    "out", "coverage", ".turbo", ".cache", "__pycache__",
}


def scan_ui(project: str | Path | None, pm: schemas.ProjectMap) -> UIInventory:
    root = project_root(project)
    frameworks = {f.name for f in pm.frameworks}
    npm_deps = _read_npm_deps(root)

    inv = UIInventory()
    if "Next.js" in frameworks:
        inv.pages.extend(_scan_nextjs(root))
    if "Nuxt" in frameworks:
        inv.pages.extend(_scan_nuxt(root))
    if "Svelte" in frameworks:
        inv.pages.extend(_scan_svelte(root))

    if "React" in frameworks and "react-router-dom" in npm_deps:
        inv.pages.extend(_scan_react_router(root))
    if "Vue" in frameworks and "vue-router" in npm_deps:
        inv.pages.extend(_scan_vue_router(root))

    # Generic filesystem fallback. Only runs when a router dep is
    # present but no router config gave us pages, so we don't fold in
    # mocks/fixtures/cms folders that happen to be called "pages".
    has_router_dep = ("react-router-dom" in npm_deps) or ("vue-router" in npm_deps)
    if has_router_dep and not inv.pages:
        inv.pages.extend(_scan_generic_filesystem(root))

    log.info("ui: %d pages discovered", len(inv.pages))
    return inv


# ---------------------------------------------------------------------
# Next.js
# ---------------------------------------------------------------------

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
    if stem.startswith(base + "/"):
        stem = stem[len(base) + 1 :]
    dot = stem.rfind(".")
    if dot != -1:
        stem = stem[:dot]
    if stem.endswith("/index") or stem == "index":
        stem = stem[:-len("index")].rstrip("/")
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


# ---------------------------------------------------------------------
# React Router (v6 / v7 dom)
# ---------------------------------------------------------------------

_REACT_ROUTE_RE = re.compile(
    r'<Route\b[^>]*?\bpath\s*=\s*"([^"]+)"[^>]*?\belement\s*=\s*\{\s*<\s*([A-Za-z_][A-Za-z0-9_]*)',
    re.DOTALL,
)
_REACT_INDEX_ROUTE_RE = re.compile(
    r'<Route\b[^>]*?\bindex\b[^>]*?\belement\s*=\s*\{\s*<\s*([A-Za-z_][A-Za-z0-9_]*)',
    re.DOTALL,
)


def _scan_react_router(root: Path) -> list[UIPage]:
    candidates = _candidate_router_files(root, extensions=(".tsx", ".jsx"))
    pages: list[UIPage] = []
    for src in candidates:
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            continue
        # Quick reject: skip files with no Route declarations at all.
        if "<Route" not in text:
            continue
        imports = _ts_default_named_imports(text, src)
        # Indexed (no path) routes — treat as parent path "/".
        for m in _REACT_INDEX_ROUTE_RE.finditer(text):
            comp = m.group(1)
            page = _route_page(root, src, "/", comp, imports, framework="React")
            if page:
                pages.append(page)
        for m in _REACT_ROUTE_RE.finditer(text):
            path, comp = m.group(1), m.group(2)
            if not path or path.strip("*") == "" or "Navigate" in comp:
                continue
            page = _route_page(root, src, _ensure_leading_slash(path), comp, imports, framework="React")
            if page:
                pages.append(page)
    return _dedupe_pages(pages)


def _ensure_leading_slash(path: str) -> str:
    if path.startswith("/"):
        return path
    return "/" + path


# ---------------------------------------------------------------------
# Vue Router
# ---------------------------------------------------------------------

_VUE_ROUTE_RE = re.compile(
    r'\{\s*path\s*:\s*[\'"]([^\'"]+)[\'"][^}]*?component\s*:\s*([A-Za-z_][A-Za-z0-9_]*)',
    re.DOTALL,
)


def _scan_vue_router(root: Path) -> list[UIPage]:
    candidates = _candidate_router_files(root, extensions=(".ts", ".js"))
    pages: list[UIPage] = []
    for src in candidates:
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            continue
        if "createRouter" not in text and "VueRouter" not in text:
            continue
        imports = _ts_default_named_imports(text, src)
        for m in _VUE_ROUTE_RE.finditer(text):
            path, comp = m.group(1), m.group(2)
            page = _route_page(root, src, _ensure_leading_slash(path), comp, imports, framework="Vue")
            if page:
                pages.append(page)
    return _dedupe_pages(pages)


# ---------------------------------------------------------------------
# Generic filesystem fallback
# ---------------------------------------------------------------------

def _scan_generic_filesystem(root: Path) -> list[UIPage]:
    """Walk the repo for `pages/` / `views/` / `routes/` directories
    and emit one UIPage per leaf component file inside them.

    Used as a last resort when router-dep is declared but no
    parseable config was found — common in custom setups.
    """
    pages: list[UIPage] = []
    for dir_path in _find_dirs_by_name(root, _GENERIC_PAGE_DIR_NAMES):
        for f in dir_path.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix not in _GENERIC_PAGE_EXTS:
                continue
            rel = f.relative_to(root).as_posix()
            stem = f.relative_to(dir_path).with_suffix("").as_posix()
            route = _ensure_leading_slash(stem.lower())
            pages.append(UIPage(framework="Unknown", route=route, source_path=rel))
    return _dedupe_pages(pages)


def _find_dirs_by_name(root: Path, names: set[str]) -> list[Path]:
    matches: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        if any(part in _IGNORE_DIR_NAMES for part in path.parts):
            continue
        if path.name in names:
            matches.append(path)
    return matches


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

def _candidate_router_files(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Find files likely to contain a router config.

    We look anywhere under the repo (covers monorepos with apps/web,
    packages/ui, etc.) and prune common build / dependency dirs.
    """
    matches: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        if any(part in _IGNORE_DIR_NAMES for part in path.parts):
            continue
        matches.append(path)
    return matches


_IMPORT_DEFAULT_RE = re.compile(
    r'import\s+([A-Za-z_][A-Za-z0-9_]*)\s+from\s+[\'"]([^\'"]+)[\'"]'
)
_IMPORT_NAMED_RE = re.compile(
    r'import\s*\{([^}]+)\}\s*from\s+[\'"]([^\'"]+)[\'"]'
)
_LAZY_IMPORT_RE = re.compile(
    r'(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:React\.)?lazy\(\s*\(\)\s*=>\s*import\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
)


def _ts_default_named_imports(text: str, src: Path) -> dict[str, Path | None]:
    """Map imported identifier → absolute resolved module path (or
    ``None`` for bare/unresolved specifiers).

    Covers default imports, named imports, and ``React.lazy`` chunks.
    """
    base_dir = src.parent
    out: dict[str, Path | None] = {}

    for m in _IMPORT_DEFAULT_RE.finditer(text):
        name, mod = m.group(1), m.group(2)
        out[name] = _resolve_import_path(base_dir, mod)

    for m in _LAZY_IMPORT_RE.finditer(text):
        name, mod = m.group(1), m.group(2)
        out[name] = _resolve_import_path(base_dir, mod)

    for m in _IMPORT_NAMED_RE.finditer(text):
        body = m.group(1)
        mod = m.group(2)
        for piece in body.split(","):
            piece = piece.strip()
            if not piece:
                continue
            local = piece.split(" as ")[-1].strip()
            if local and local[0].isalpha():
                out[local] = _resolve_import_path(base_dir, mod)
    return out


def _resolve_import_path(base_dir: Path, module: str) -> Path | None:
    """Best-effort resolution of a JS/TS import specifier to an
    absolute path. Returns ``None`` for bare specifiers (third-party
    packages, aliased paths the linter can't resolve).
    """
    if not module.startswith((".", "/")):
        return None
    cwd = base_dir.resolve()
    target = (cwd / module).resolve()
    candidates: list[Path] = [target]
    for ext in (".tsx", ".jsx", ".ts", ".js", ".vue"):
        candidates.append(target.with_suffix(ext))
    for ext in (".tsx", ".jsx", ".ts", ".js"):
        candidates.append(target / f"index{ext}")
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _is_under(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _rel_to_root(root: Path, abs_path: Path) -> str:
    try:
        return abs_path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return abs_path.as_posix()


def _route_page(
    root: Path,
    src: Path,
    route: str,
    comp_name: str,
    imports: dict[str, Path | None],
    framework: str,
) -> UIPage | None:
    src_rel = _rel_to_root(root, src)
    resolved = imports.get(comp_name)
    source_path = _rel_to_root(root, resolved) if resolved is not None else src_rel
    return UIPage(framework=framework, route=route, source_path=source_path)


def _dedupe_pages(pages: list[UIPage]) -> list[UIPage]:
    seen: set[tuple[str, str]] = set()
    out: list[UIPage] = []
    for p in pages:
        key = (p.route, p.source_path)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
