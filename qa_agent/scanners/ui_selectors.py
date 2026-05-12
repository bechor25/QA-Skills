"""UI selector scanner.

Walks the project's UI source files (React/Vue/Svelte/Angular) and
captures stable selectors the body author can use without re-reading
the codebase. Output: state/ui_selectors.json keyed by capability.

The scanner is intentionally regex-based: it must run in <2s even on
large monorepos. Higher-fidelity parsing belongs in the body author
sub-agent.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ..state import schemas


_UI_EXTS = {".tsx", ".jsx", ".vue", ".svelte", ".html"}
_SKIP_DIRS = {"node_modules", ".next", "dist", "build", "out", ".turbo", ".qa-agent"}

# Matches: data-testid="x", data-test-id="x", data-test="x", data-cy="x"
_TESTID_RE = re.compile(r"""data-(?:testid|test-id|test|cy)\s*=\s*["']([^"']+)["']""")

# Matches: aria-label="x" (only on interactive elements, captured generically)
_ARIA_LABEL_RE = re.compile(r"""aria-label\s*=\s*["']([^"']+)["']""")

# Matches: id="x" — lower-fidelity, used only if no test-id present in file.
_ID_RE = re.compile(r"""\sid\s*=\s*["']([a-zA-Z][\w-]{2,})["']""")

_CAPABILITY_HINT_RE = re.compile(r"[/\\]")


def scan_ui_selectors(project_root: Path, project_map: schemas.ProjectMap) -> schemas.UISelectorMap:
    """Return a UISelectorMap built from project_map's UI files."""
    by_cap: dict[str, list[schemas.UISelector]] = {}

    for entry in project_map.files:
        rel = entry.path
        if entry.is_test:
            continue
        if not any(rel.endswith(ext) for ext in _UI_EXTS):
            continue
        if any(seg in rel.split("/") for seg in _SKIP_DIRS):
            continue
        abs_path = project_root / rel
        try:
            text = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        capability = _capability_from_path(rel)
        bucket = by_cap.setdefault(capability, [])
        bucket.extend(_extract(text, rel))

    # Cap per-capability list size to keep state files small. Stable
    # sort by selector for diffability.
    for cap, sels in by_cap.items():
        sels.sort(key=lambda s: (s.file, s.line or 0, s.selector))
        by_cap[cap] = _dedupe(sels)[:200]

    return schemas.UISelectorMap(built_at=datetime.now(timezone.utc), by_capability=by_cap)


def _extract(text: str, rel_path: str) -> list[schemas.UISelector]:
    out: list[schemas.UISelector] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in _TESTID_RE.finditer(line):
            val = m.group(1)
            out.append(schemas.UISelector(
                selector=f"[data-testid='{val}']",
                label=val,
                file=rel_path,
                line=i,
                context=_truncate(line),
            ))
        for m in _ARIA_LABEL_RE.finditer(line):
            val = m.group(1)
            out.append(schemas.UISelector(
                selector=f"[aria-label='{val}']",
                role="",
                label=val,
                file=rel_path,
                line=i,
                context=_truncate(line),
            ))
    # Only fall back to id-based selectors when nothing better exists in the file.
    if not out:
        for i, line in enumerate(text.splitlines(), start=1):
            for m in _ID_RE.finditer(line):
                val = m.group(1)
                out.append(schemas.UISelector(
                    selector=f"#{val}",
                    label=val,
                    file=rel_path,
                    line=i,
                    context=_truncate(line),
                ))
    return out


def _dedupe(items: list[schemas.UISelector]) -> list[schemas.UISelector]:
    seen: set[tuple[str, str]] = set()
    out: list[schemas.UISelector] = []
    for s in items:
        key = (s.selector, s.file)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _truncate(line: str, limit: int = 120) -> str:
    s = line.strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _capability_from_path(rel: str) -> str:
    """Heuristic: pick the first meaningful path segment as capability.

    Examples:
      apps/web/src/pages/Login.tsx -> login
      apps/web/src/features/auth/LoginForm.tsx -> auth
      apps/web/src/admin/Dashboard.tsx -> admin
    """
    segs = [s for s in _CAPABILITY_HINT_RE.split(rel) if s]
    # Drop common scaffolding prefixes.
    drop = {"apps", "src", "packages", "web", "client", "frontend", "ui", "pages", "features", "components", "views"}
    for seg in segs[:-1]:  # skip the filename itself
        if seg.lower() not in drop:
            return seg.lower()
    return "other"
