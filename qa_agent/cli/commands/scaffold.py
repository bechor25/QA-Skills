"""`qa-agent scaffold` — emit grouped test files.

Reads sharded scenarios from `state/scenarios/<capability>.json` and
groups them by `(capability, category)`. Each group becomes a single
test file under `tests/qa-agent/<category>/<capability>.{spec.ts|py}`
containing one stub per scenario, marked with ``QA-AGENT-BODY ::
<scenario_id> :: <title>``. The qa-body-author sub-agent then fills
the stubs in place.

Falls back to the legacy top-level `scenarios.json` when no shards
exist.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ...generators import harness, scaffolds
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
    api_runner = pm.test_runners.get("api")
    plan = sm.load(schemas.TestDataPlan)
    hints = scaffolds.ScaffoldHints.from_plan(plan)
    probe_only = bool(getattr(args, "probe_only", False))

    log.info(
        "scaffold: language=%s api_runner=%s ui_runner=%s probe_only=%s",
        target_language,
        api_runner or "(default)",
        pm.test_runners.get("ui") or "(none)",
        probe_only,
    )

    shards = sm.list_scenario_capabilities()
    if shards:
        log.info("scaffold: using sharded scenarios for %d capabilities", len(shards))
        entries, files_written = _scaffold_from_shards(
            sm, root, shards, target_language, api_runner, hints, probe_only=probe_only
        )
    else:
        legacy = sm.load(schemas.Scenarios)
        log.info(
            "scaffold: no shards found, falling back to legacy scenarios.json (%d entries)",
            len(legacy.entries),
        )
        entries, files_written = _scaffold_from_legacy(
            root, legacy, target_language, api_runner, hints, probe_only=probe_only
        )

    generated = schemas.GeneratedTests(built_at=datetime.now(timezone.utc), entries=entries)
    sm.save(generated)
    log.info(
        "scaffold: wrote %d files holding %d scenario stubs (generated_tests.json updated)",
        files_written,
        len(entries),
    )

    emitted_paths = [e.path for e in entries]
    harness_files = harness.emit_harness_files(root, pm, emitted_paths)
    if harness_files:
        log.info("scaffold: harness files emitted: %s", harness_files)

    log.info("scaffold: READY. Next: fan out qa-body-author per (capability, category) file.")
    return 0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _target_language(pm: schemas.ProjectMap) -> str:
    py = pm.languages.get("python", 0)
    ts = pm.languages.get("typescript", 0) + pm.languages.get("javascript", 0)
    return "python" if py > ts else "typescript"


def _scaffold_from_shards(
    sm: StateManager,
    root: Path,
    shards: list[str],
    target_language: str,
    api_runner: str | None,
    hints: scaffolds.ScaffoldHints,
    probe_only: bool = False,
) -> tuple[list[schemas.GeneratedTest], int]:
    grouped: dict[tuple[str, str], list[schemas.RichScenario]] = defaultdict(list)
    for cap in shards:
        sh = sm.load_capability_scenarios(cap)
        if sh is None:
            continue
        is_probe_file = bool(getattr(sh, "mode", "") == "probe")
        for sc in sh.scenarios:
            tags = list(getattr(sc, "tags", []) or [])
            sc_is_probe = is_probe_file or "probe" in tags
            if probe_only and not sc_is_probe:
                continue
            if (not probe_only) and sc_is_probe:
                # Real-run scaffolding skips probe-tagged scenarios — they
                # were throwaway. The next scenario-author pass overwrites
                # the capability's scenarios file with the full set.
                continue
            grouped[(sc.capability, sc.category)].append(sc)

    return _emit_groups(root, grouped, target_language, api_runner, hints, probe=probe_only)


def _scaffold_from_legacy(
    root: Path,
    legacy: schemas.Scenarios,
    target_language: str,
    api_runner: str | None,
    hints: scaffolds.ScaffoldHints,
    probe_only: bool = False,
) -> tuple[list[schemas.GeneratedTest], int]:
    grouped: dict[tuple[str, str], list[schemas.Scenario]] = defaultdict(list)
    for sc in legacy.entries:
        if probe_only:
            # Legacy scenarios.json has no tags concept; skip the
            # probe-only path entirely.
            continue
        grouped[(sc.capability, sc.category)].append(sc)
    return _emit_groups(
        root,
        grouped,
        target_language,
        api_runner,
        hints,
        feature_id_fn=lambda sc: sc.feature_id,
        probe=probe_only,
    )


def _emit_groups(
    root: Path,
    grouped: dict[tuple[str, str], list],
    target_language: str,
    api_runner: str | None,
    hints: scaffolds.ScaffoldHints,
    feature_id_fn=None,
    probe: bool = False,
) -> tuple[list[schemas.GeneratedTest], int]:
    entries: list[schemas.GeneratedTest] = []
    files_written = 0
    for (cap, category), scenarios in sorted(grouped.items()):
        stubs = [
            scaffolds.ScenarioStub(id=sc.id, title=_title_for(sc))
            for sc in scenarios
        ]
        gf = scaffolds.emit_scaffold_group(
            capability=cap,
            category=category,
            scenarios=stubs,
            language=target_language,
            runner=api_runner,
            hints=hints,
            probe=probe,
        )
        write_file(root, gf)
        files_written += 1
        for sc in scenarios:
            entries.append(
                schemas.GeneratedTest(
                    scenario_id=sc.id,
                    feature_id=(feature_id_fn(sc) if feature_id_fn else f"feat::{cap}"),
                    category=category,
                    path=gf.rel_path,
                    framework=gf.framework,
                    language=gf.language,
                    summary=_title_for(sc),
                )
            )
    return entries, files_written


def _title_for(sc) -> str:
    """RichScenario.title vs legacy Scenario.title — both expose `.title`,
    but legacy may fall back to `<cap> <category>`.
    """
    return sc.title or f"{sc.capability} {sc.category}"
