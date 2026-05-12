"""UI selector scanner.

Walks the project's UI source files (React/Vue/Svelte/Angular) and
captures stable selectors the body author can use without re-reading
the codebase. Output: state/ui_selectors.json keyed by capability.

Capability mapping reuses the shared keyword dictionary
(`qa_agent.shared.capabilities`) so the same `/login` page resolves
to `auth` here, in the KG, in the strategy, and in the contracts.
The legacy path-segment heuristic was lossy — every page under a
`Jobs/` folder ended up under capability `jobs` instead of being
fanned out to the capabilities it actually serves.

The scanner is intentionally regex-based: it must run in <2s even on
large monorepos. Higher-fidelity parsing belongs in the body author
sub-agent.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ..shared.capabilities import classify_capabilities
from ..state import schemas


_UI_EXTS = {".tsx", ".jsx", ".vue", ".svelte", ".html"}
_SKIP_DIRS = {"node_modules", ".next", "dist", "build", "out", ".turbo", ".qa-agent"}

# Matches: data-testid="x", data-test-id="x", data-test="x", data-cy="x"
_TESTID_RE = re.compile(r"""data-(?:testid|test-id|test|cy)\s*=\s*["']([^"']+)["']""")

# Matches: aria-label="x" (only on interactive elements, captured generically)
_ARIA_LABEL_RE = re.compile(r"""aria-label\s*=\s*["']([^"']+)["']""")

# Matches: id="x" — lower-fidelity, used only if no test-id present in file.
_ID_RE = re.compile(r"""\sid\s*=\s*["']([a-zA-Z][\w-]{2,})["']""")


def scan_ui_selectors(
    project_root: Path,
    project_map: schemas.ProjectMap,
    knowledge_graph: schemas.KnowledgeGraph | None = None,
) -> schemas.UISelectorMap:
    """Return a UISelectorMap built from project_map's UI files.

    Each UI file's selectors are fanned out to **every** capability
    that matches its path/content (multi-bucket assignment). When a
    knowledge_graph is provided, file→capability mappings from KG
    module→feature→capability take precedence; the shared keyword
    classifier is the fallback.
    """
    by_cap: dict[str, list[schemas.UISelector]] = {}

    kg_index = _build_kg_capability_index(knowledge_graph) if knowledge_graph else {}

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

        capabilities = _capabilities_for_file(rel, text, kg_index)
        selectors = _extract(text, rel)
        if not selectors:
            continue
        for cap in capabilities:
            bucket = by_cap.setdefault(cap, [])
            bucket.extend(selectors)

    # Cap per-capability list size to keep state files small. Stable
    # sort by selector for diffability.
    for cap, sels in by_cap.items():
        sels.sort(key=lambda s: (s.file, s.line or 0, s.selector))
        by_cap[cap] = _dedupe(sels)[:200]

    return schemas.UISelectorMap(built_at=datetime.now(timezone.utc), by_capability=by_cap)


def _build_kg_capability_index(kg: schemas.KnowledgeGraph) -> dict[str, list[str]]:
    """Return a `file_path → [capability, ...]` mapping derived from the KG.

    The KG carries `feature.capabilities[]` and each feature lists
    `module_ids[]`; modules carry `path`. Composing these gives a
    direct mapping from any source file to the capabilities it serves.
    """
    feature_caps: dict[str, list[str]] = {f.id: list(f.capabilities) for f in kg.features}
    out: dict[str, list[str]] = {}
    for mod in kg.modules:
        caps: list[str] = []
        for fid in mod.features:
            for cap in feature_caps.get(fid, []):
                if cap not in caps:
                    caps.append(cap)
        if caps:
            out[mod.path] = caps
    return out


def _capabilities_for_file(rel_path: str, text: str, kg_index: dict[str, list[str]]) -> list[str]:
    """Pick capabilities for a UI file. KG hits first, keyword fallback."""
    # 1. Exact KG match.
    if rel_path in kg_index:
        return kg_index[rel_path]
    # 2. KG prefix match — the file lives under a directory the KG indexed.
    for kg_path, caps in kg_index.items():
        if rel_path.startswith(kg_path.rsplit("/", 1)[0] + "/") and kg_path != rel_path:
            return caps
    # 3. Shared keyword classifier on path + the first ~200 chars of text.
    hint = rel_path + " " + (text[:200] if text else "")
    return classify_capabilities(hint)


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


