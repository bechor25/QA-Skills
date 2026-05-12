"""App-entry detection.

Generators need the path to an importable Express/Fastify/Koa `app`
module so the generated tests can do `import app from "../../qa-agent.app"`.

Strategy (best-effort, deterministic):

1. Read root `package.json` and any monorepo workspaces.
2. For each candidate package, search `src/app.{ts,js}` first, then
   `src/index.{ts,js}` and the package's `main` field.
3. Pick the first file that contains BOTH a server framework import
   (express/fastify/koa) AND a `default export` (or `module.exports = app`).

Returns a `AppEntry` describing the absolute path and the module-style
specifier to import from. When nothing fits, returns `None`.

For Python apps, the same idea applies but with `fastapi`/`flask` and
the file exposes `app = FastAPI(...)`. Python detection is added when
generators start emitting pytest tests that need the entry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..shared.logging import get_logger

log = get_logger("qa_agent.context.app_entry")


@dataclass(slots=True)
class AppEntry:
    """An importable application module for test harnesses."""

    abs_path: Path            # file containing the exported app
    rel_path: str             # path relative to project root, posix-style
    language: str             # "typescript" | "javascript" | "python"
    framework: str            # "express" | "fastify" | "koa" | "fastapi" | "flask"
    has_default_export: bool  # for TS/JS — drives `import app` vs `import {app}`


_TS_FRAMEWORK_RES = [
    ("express",  re.compile(r"""from\s+['"]express['"]|require\(['"]express['"]\)""")),
    ("fastify",  re.compile(r"""from\s+['"]fastify['"]|require\(['"]fastify['"]\)""")),
    ("koa",      re.compile(r"""from\s+['"]koa['"]|require\(['"]koa['"]\)""")),
    ("nestjs",   re.compile(r"""from\s+['"]@nestjs/core['"]""")),
]

_PY_FRAMEWORK_RES = [
    ("fastapi", re.compile(r"^\s*from\s+fastapi\s+import|^\s*import\s+fastapi", re.MULTILINE)),
    ("flask",   re.compile(r"^\s*from\s+flask\s+import|^\s*import\s+flask", re.MULTILINE)),
]

_TS_DEFAULT_EXPORT = re.compile(r"^\s*export\s+default\s+", re.MULTILINE)
_TS_NAMED_APP_EXPORT = re.compile(r"^\s*export\s+(?:const|let|var)\s+app\b", re.MULTILINE)
_TS_MODULE_EXPORTS = re.compile(r"module\.exports\s*=\s*\w+")


def detect_app_entry(project_root: Path) -> AppEntry | None:
    """Return the best app-entry candidate, or None if none found."""
    candidates = list(_node_candidates(project_root)) + list(_python_candidates(project_root))
    for cand in candidates:
        entry = _classify_candidate(cand, project_root)
        if entry is not None:
            log.info("app_entry: detected %s (%s/%s)", entry.rel_path, entry.language, entry.framework)
            return entry
    log.info("app_entry: no candidate matched (scanned %d files)", len(candidates))
    return None


def _node_candidates(project_root: Path) -> list[Path]:
    """Scan root + workspace package.json files for app entry candidates."""
    out: list[Path] = []
    pkg_paths = [project_root / "package.json"]
    pkg_paths.extend(_workspace_package_paths(project_root))

    seen: set[Path] = set()
    for pkg_path in pkg_paths:
        if not pkg_path.is_file():
            continue
        pkg_dir = pkg_path.parent
        for rel in ("src/app.ts", "src/app.js", "src/server.ts", "src/server.js",
                    "src/index.ts", "src/index.js", "app.ts", "app.js",
                    "index.ts", "index.js"):
            cand = pkg_dir / rel
            if cand.is_file() and cand not in seen:
                seen.add(cand)
                out.append(cand)

        # `main` field
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        main = pkg.get("main")
        if isinstance(main, str):
            for ext in ("", ".ts", ".js"):
                cand = (pkg_dir / (main + ext)).resolve()
                if cand.is_file() and cand not in seen:
                    seen.add(cand)
                    out.append(cand)
    return out


def _workspace_package_paths(project_root: Path) -> list[Path]:
    """Return package.json paths reachable via npm/yarn/pnpm/turbo workspaces."""
    out: list[Path] = []
    root_pkg = project_root / "package.json"
    if not root_pkg.is_file():
        return out
    try:
        data = json.loads(root_pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    workspaces = data.get("workspaces")
    patterns: list[str] = []
    if isinstance(workspaces, list):
        patterns.extend(str(p) for p in workspaces)
    elif isinstance(workspaces, dict):
        packages = workspaces.get("packages")
        if isinstance(packages, list):
            patterns.extend(str(p) for p in packages)

    # Default common monorepo dirs even without workspaces config.
    if not patterns:
        patterns = ["apps/*", "packages/*", "services/*"]

    for pat in patterns:
        for entry in project_root.glob(f"{pat}/package.json"):
            out.append(entry)
    return out


def _python_candidates(project_root: Path) -> list[Path]:
    """Scan for `app.py` / `main.py` containing fastapi/flask imports."""
    out: list[Path] = []
    for name in ("app.py", "main.py", "src/app.py", "src/main.py"):
        cand = project_root / name
        if cand.is_file():
            out.append(cand)
    return out


def _classify_candidate(path: Path, project_root: Path) -> AppEntry | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    suffix = path.suffix.lower()
    if suffix in {".ts", ".tsx", ".js", ".mjs", ".cjs"}:
        return _classify_node(path, text, project_root)
    if suffix == ".py":
        return _classify_python(path, text, project_root)
    return None


def _classify_node(path: Path, text: str, project_root: Path) -> AppEntry | None:
    framework = next((name for name, pat in _TS_FRAMEWORK_RES if pat.search(text)), None)
    if framework is None:
        return None
    has_default = bool(_TS_DEFAULT_EXPORT.search(text))
    has_named_app = bool(_TS_NAMED_APP_EXPORT.search(text))
    has_module_exports = bool(_TS_MODULE_EXPORTS.search(text))
    if not (has_default or has_named_app or has_module_exports):
        return None
    rel = path.relative_to(project_root).as_posix()
    language = "typescript" if path.suffix.lower() in {".ts", ".tsx"} else "javascript"
    return AppEntry(
        abs_path=path,
        rel_path=rel,
        language=language,
        framework=framework,
        has_default_export=has_default,
    )


def _classify_python(path: Path, text: str, project_root: Path) -> AppEntry | None:
    framework = next((name for name, pat in _PY_FRAMEWORK_RES if pat.search(text)), None)
    if framework is None:
        return None
    if "app =" not in text and "app=" not in text:
        return None
    rel = path.relative_to(project_root).as_posix()
    return AppEntry(
        abs_path=path,
        rel_path=rel,
        language="python",
        framework=framework,
        has_default_export=False,
    )
