"""Shared helpers for test generators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..state import schemas


@dataclass(slots=True)
class GeneratedFile:
    """One file emitted by a generator."""

    rel_path: str          # path relative to project root
    body: str
    framework: str
    language: str


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, default: str = "scenario") -> str:
    """Lowercase, dash-separated slug suitable for filenames."""
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or default


def write_file(project_root: Path, gf: GeneratedFile) -> Path:
    """Write a generated file under the project root, creating parents."""
    abs_path = project_root / gf.rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(gf.body, encoding="utf-8")
    return abs_path


_PATH_PARAM_EXPRESS = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_PATH_PARAM_CURLY = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def materialize_path(pattern: str) -> str:
    """Replace route params with safe sample values.

    Express-style `:id`, FastAPI/Flask `{id}` -> `1` for numeric-looking
    names, `'sample'` otherwise. Patterns like `*` are left untouched.
    """
    def sub(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if any(k in name for k in ("id", "num", "count", "page")):
            return "1"
        return "sample"

    out = _PATH_PARAM_EXPRESS.sub(sub, pattern or "/")
    out = _PATH_PARAM_CURLY.sub(sub, out)
    return out or "/"


def effective_request(route: schemas.RouteHint | None, default_method: str = "GET") -> tuple[str, str]:
    """Return (method, path) for a request. Falls back to GET / when no route."""
    if route is None:
        return default_method, "/"
    method = route.method.upper()
    if method in {"USE", "ROUTE", "DECORATOR", "UNKNOWN"}:
        # Mount points / decorator names — fall back to GET on the same path.
        method = "GET"
    return method, materialize_path(route.pattern)
