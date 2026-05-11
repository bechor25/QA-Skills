"""Incremental retry engine.

Given a re-run scope, return the list of GeneratedTest paths to execute:

  - scope='all'     → every entry
  - scope='failed'  → entries whose latest history record reports failure
  - scope='flaky'   → entries listed in flaky_state.json
  - scope='changed' → entries whose source modules changed since the
                      previous run, propagating through the dependency
                      graph (one hop)
"""

from __future__ import annotations

from pathlib import Path

from ..shared.git import changed_files, current_sha
from ..shared.logging import get_logger
from ..state import schemas
from ..state.manager import StateManager

log = get_logger("qa_agent.agent.retry_engine")


def scope_paths(
    project_root: Path,
    scope: str,
) -> list[str]:
    """Return repo-relative GeneratedTest paths that satisfy `scope`."""
    sm = StateManager(str(project_root))
    tests = sm.load(schemas.GeneratedTests)
    if not tests.entries:
        return []

    if scope == "all":
        return [t.path for t in tests.entries]
    if scope == "failed":
        return _failed(sm.load(schemas.ExecutionHistory))
    if scope == "flaky":
        return _flaky(sm.load(schemas.FlakyState), tests)
    if scope == "changed":
        return _changed(project_root, sm.load(schemas.DependencyGraph), tests)
    log.warning("retry: unknown scope=%s — returning all", scope)
    return [t.path for t in tests.entries]


def _failed(history: schemas.ExecutionHistory) -> list[str]:
    if not history.records:
        return []
    last_run = history.records[-1].run_id
    out: set[str] = set()
    for rec in reversed(history.records):
        if rec.run_id != last_run:
            break
        if rec.failed:
            out.update(rec.test_files)
    return sorted(out)


def _flaky(state: schemas.FlakyState, tests: schemas.GeneratedTests) -> list[str]:
    flaky_ids = {e.test_id for e in state.entries}
    return [t.path for t in tests.entries if t.path in flaky_ids]


def _changed(
    project_root: Path,
    dep: schemas.DependencyGraph,
    tests: schemas.GeneratedTests,
) -> list[str]:
    sha = current_sha(project_root)
    if not sha:
        log.info("retry: no git context; falling back to 'all'")
        return [t.path for t in tests.entries]
    changed = set(changed_files(project_root, "HEAD~1"))
    if not changed:
        return []

    # Walk dep graph one hop: a test is in scope if it (or any module it
    # imports) was changed. Test files aren't in the dependency graph by
    # default, so we use a stem match.
    impacted = set(changed)
    by_id = {m.id: m for m in dep.modules}
    for mod in dep.modules:
        for imp in mod.imports:
            stem = imp.split(".")[-1].split("/")[-1]
            if any(c.endswith(stem) or stem in c for c in changed):
                impacted.add(mod.id)

    out: list[str] = []
    for t in tests.entries:
        # Heuristic: include test if its filename references a changed
        # module path's stem, or if the feature directory matches.
        if any(impacted_stem(t.path) in i for i in impacted):
            out.append(t.path)
    return out


def impacted_stem(test_path: str) -> str:
    name = test_path.split("/")[-1]
    for prefix in ("test_", ""):
        if name.startswith(prefix):
            name = name[len(prefix):]
    for suffix in (".py", ".spec.ts", ".spec.tsx", ".spec.js"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
