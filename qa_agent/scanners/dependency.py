"""Dependency graph scanner.

Builds the per-module import graph from parsed files. The graph is the
backbone of incremental re-runs (Phase 5) and the relevance engine
(Phase 1.12).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..parsers.python_ast import parse_python_file
from ..parsers.ts_morph_bridge import parse_ts_files
from ..parsers.types import ParsedFile
from ..shared.logging import get_logger
from ..shared.paths import project_root
from ..state import schemas

log = get_logger("qa_agent.scanners.dependency")


def build_dependency_graph(
    project: str | Path | None,
    pm: schemas.ProjectMap,
) -> schemas.DependencyGraph:
    """Return a DependencyGraph derived from `pm.files`.

    Each file becomes a ModuleNode keyed by its relative path. `imports`
    stores raw import names; `imported_by` is filled by reverse-walking.
    """
    root = project_root(project)
    parsed = _parse_all(root, pm.files)
    modules = {
        pf.path: schemas.ModuleNode(
            id=pf.path,
            path=pf.path,
            language=pf.language,
            imports=pf.imports,
        )
        for pf in parsed
    }
    _fill_reverse_edges(modules)

    log.info("dependency: %d modules indexed", len(modules))
    return schemas.DependencyGraph(
        built_at=datetime.now(timezone.utc),
        modules=list(modules.values()),
    )


def _parse_all(root: Path, files: list[schemas.FileEntry]) -> Iterable[ParsedFile]:
    py_files = [f.path for f in files if f.language == "python" and not f.is_test]
    ts_files = [
        f.path
        for f in files
        if f.language in {"typescript", "javascript"} and not f.is_test
    ]
    parsed: list[ParsedFile] = []
    for rel in py_files:
        parsed.append(parse_python_file(root, rel))
    if ts_files:
        parsed.extend(parse_ts_files(root, ts_files))
    return parsed


def _fill_reverse_edges(modules: dict[str, schemas.ModuleNode]) -> None:
    """Add reverse-edge `imported_by` by best-effort matching.

    Imports rarely match a full repo-relative path 1:1 (they use module
    paths, package aliases, etc.). We match on the last path segment as
    a cheap heuristic — accurate enough for incremental-rerun scoping.
    """
    suffix_index: dict[str, list[str]] = {}
    for mod_id, mod in modules.items():
        stem = Path(mod.path).stem
        suffix_index.setdefault(stem, []).append(mod_id)

    for mod_id, mod in modules.items():
        for imp in mod.imports:
            target_stem = imp.split(".")[-1].split("/")[-1]
            for candidate in suffix_index.get(target_stem, []):
                if candidate == mod_id:
                    continue
                tgt = modules[candidate]
                if mod_id not in tgt.imported_by:
                    tgt.imported_by.append(mod_id)
