"""Non-LLM summarizers.

Produce deterministic text summaries from scanner output. The LLM later
consumes these — they never replace the LLM but they massively shrink
the prompt surface and keep behavior reproducible.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from ..state import schemas


def summarize_project(pm: schemas.ProjectMap, dep: schemas.DependencyGraph) -> str:
    """A 1-paragraph snapshot of what this project is."""
    langs = ", ".join(f"{name}({count})" for name, count in sorted(pm.languages.items(), key=lambda kv: -kv[1]))
    frameworks = ", ".join(sorted({f.name for f in pm.frameworks}))
    pms = ", ".join(pm.package_managers) or "none"
    return (
        f"Project at {pm.project_root} — "
        f"{len(pm.files)} source files across languages: {langs or 'unknown'}. "
        f"Frameworks: {frameworks or 'none detected'}. "
        f"Package managers: {pms}. "
        f"{len(dep.modules)} modules indexed in the dependency graph."
    )


def summarize_modules(
    pm: schemas.ProjectMap,
    dep: schemas.DependencyGraph,
) -> list[schemas.ModuleSummary]:
    """Per-module summaries grouped by top-level directory.

    Each top-level dir becomes a module; the summary lists languages,
    file count, and (if any) imported packages so the relevance engine
    can quickly route a capability to a candidate module.
    """
    groups: dict[str, list[schemas.FileEntry]] = {}
    for f in pm.files:
        head = _top_dir(f.path)
        groups.setdefault(head, []).append(f)

    dep_index: dict[str, schemas.ModuleNode] = {m.path: m for m in dep.modules}
    out: list[schemas.ModuleSummary] = []
    for head, files in sorted(groups.items()):
        langs = Counter(f.language for f in files)
        imports: Counter[str] = Counter()
        for f in files:
            node = dep_index.get(f.path)
            if node:
                for imp in node.imports:
                    imports[imp.split(".")[0]] += 1
        top_imports = ", ".join(p for p, _ in imports.most_common(5))
        summary = (
            f"{head} ({len(files)} files, languages: "
            f"{', '.join(f'{n}={c}' for n, c in langs.most_common())})."
        )
        if top_imports:
            summary += f" Top imports: {top_imports}."
        out.append(
            schemas.ModuleSummary(
                id=head,
                path=head,
                summary=summary,
                features=[],
            )
        )
    return out


def _top_dir(rel_path: str) -> str:
    head = rel_path.split("/", 1)[0]
    return head if head else "."
