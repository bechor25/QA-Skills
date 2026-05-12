"""`qa-agent scaffold` — emit empty test files for every scenario.

Reads sharded scenarios from `state/scenarios/<capability>.json`
(produced by qa-scenario-author), the test_data_plan, and the project
map, then writes one scaffold file per scenario under
`tests/qa-agent/<category>/`.

The scaffolded files contain imports + a single `it.todo` /
`pytest.skip` placeholder marked with `QA-AGENT-BODY`. The
qa-body-author sub-agent fills them in afterwards.

Falls back to the legacy top-level `scenarios.json` when no shards
exist — so this command also works for projects that haven't been
through enrichment yet.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from ...generators import scaffolds
from ...generators.base import write_file
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.scaffold")


def run(args: argparse.Namespace) -> int:
    project = args.project
    root = project_root(project)
    sm = StateManager(project)

    pm = sm.project_map()
    target_language = _target_language(pm)
    plan = sm.load(schemas.TestDataPlan)
    hints = scaffolds.ScaffoldHints.from_plan(plan)

    shards = sm.list_scenario_capabilities()
    if shards:
        log.info("scaffold: using sharded scenarios for %d capabilities", len(shards))
        entries, written = _scaffold_from_shards(sm, root, shards, target_language, hints)
    else:
        legacy = sm.load(schemas.Scenarios)
        log.info("scaffold: no shards found, falling back to legacy scenarios.json (%d entries)",
                 len(legacy.entries))
        entries, written = _scaffold_from_legacy(sm, root, legacy, target_language, hints)

    generated = schemas.GeneratedTests(built_at=datetime.now(timezone.utc), entries=entries)
    sm.save(generated)
    log.info("scaffold: wrote %d scaffold files (generated_tests.json updated)", written)
    log.info("scaffold: READY. Next: fan out qa-body-author per (capability, category) batch.")
    return 0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _target_language(pm: schemas.ProjectMap) -> str:
    """Pick `python` when py files dominate, otherwise `typescript`."""
    py = pm.languages.get("python", 0)
    ts = pm.languages.get("typescript", 0) + pm.languages.get("javascript", 0)
    return "python" if py > ts else "typescript"


def _scaffold_from_shards(
    sm: StateManager,
    root,
    shards: list[str],
    target_language: str,
    hints: scaffolds.ScaffoldHints,
) -> tuple[list[schemas.GeneratedTest], int]:
    written = 0
    entries: list[schemas.GeneratedTest] = []
    for cap in shards:
        sh = sm.load_capability_scenarios(cap)
        if sh is None:
            continue
        for sc in sh.scenarios:
            gf = scaffolds.emit_scaffold(
                scenario_id=sc.id,
                capability=sc.capability,
                category=sc.category,
                title=sc.title,
                language=target_language,
                hints=hints,
            )
            write_file(root, gf)
            entries.append(schemas.GeneratedTest(
                scenario_id=sc.id,
                feature_id=f"feat::{sc.capability}",
                category=sc.category,
                path=gf.rel_path,
                framework=gf.framework,
                language=gf.language,
                summary=sc.title,
            ))
            written += 1
    return entries, written


def _scaffold_from_legacy(
    sm: StateManager,
    root,
    legacy: schemas.Scenarios,
    target_language: str,
    hints: scaffolds.ScaffoldHints,
) -> tuple[list[schemas.GeneratedTest], int]:
    entries: list[schemas.GeneratedTest] = []
    written = 0
    for sc in legacy.entries:
        gf = scaffolds.emit_scaffold(
            scenario_id=sc.id,
            capability=sc.capability,
            category=sc.category,
            title=sc.title or f"{sc.capability} {sc.category}",
            language=target_language,
            hints=hints,
        )
        write_file(root, gf)
        entries.append(schemas.GeneratedTest(
            scenario_id=sc.id,
            feature_id=sc.feature_id,
            category=sc.category,
            path=gf.rel_path,
            framework=gf.framework,
            language=gf.language,
            summary=sc.title,
        ))
        written += 1
    return entries, written
