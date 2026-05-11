"""Generation loop.

Wires the per-category generators, runs the critic, and persists state:
  scenarios -> generators -> write files -> critic -> save GeneratedTests + Critique.

The loop is non-LLM and deterministic. The LLM-augmented variant (Phase
7) replaces just the generator step with prompt-driven bodies validated
by the same critic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..generators.accessibility_tests import emit_accessibility_tests
from ..generators.api_tests import emit_api_tests
from ..generators.base import GeneratedFile, write_file
from ..generators.performance_tests import emit_performance_tests
from ..generators.regression_tests import emit_regression_tests
from ..generators.security_tests import emit_security_tests
from ..generators.ui_tests import emit_ui_tests
from ..shared.logging import get_logger
from ..state import schemas
from .test_critic import critique_files

log = get_logger("qa_agent.quality.generation_loop")


def run_generation_loop(
    project_root: Path,
    scenarios: schemas.Scenarios,
    pm: schemas.ProjectMap,
) -> tuple[schemas.GeneratedTests, schemas.Critique]:
    """Generate, write, and critique. Returns the two new state models."""
    target_language = _pick_language(pm)
    log.info("generation: target_language=%s", target_language)

    files: list[GeneratedFile] = []
    files.extend(emit_api_tests(scenarios.entries, target_language))
    files.extend(emit_ui_tests(scenarios.entries))
    files.extend(emit_security_tests(scenarios.entries, target_language))
    files.extend(emit_accessibility_tests(scenarios.entries))
    files.extend(emit_performance_tests(scenarios.entries))
    files.extend(emit_regression_tests(scenarios.entries, target_language))

    written: list[schemas.GeneratedTest] = []
    by_path: dict[str, GeneratedFile] = {gf.rel_path: gf for gf in files}
    scenario_by_path: dict[str, schemas.Scenario] = {}
    for gf in files:
        # Map back to the originating scenario by id substring in body.
        # (Each generator embeds the scenario id once in the body header.)
        sid = _extract_scenario_id(gf.body)
        sc = next((s for s in scenarios.entries if s.id == sid), None)
        if sc is None:
            continue
        scenario_by_path[gf.rel_path] = sc
        write_file(project_root, gf)
        written.append(
            schemas.GeneratedTest(
                scenario_id=sc.id,
                feature_id=sc.feature_id,
                category=sc.category,
                path=gf.rel_path,
                framework=gf.framework,
                language=gf.language,
                summary=sc.title,
            )
        )

    log.info("generation: wrote %d test files", len(written))
    generated = schemas.GeneratedTests(
        built_at=datetime.now(timezone.utc),
        entries=written,
    )
    critique = critique_files(project_root, generated)
    return generated, critique


def _pick_language(pm: schemas.ProjectMap) -> str:
    """Pick the dominant generator language for the project."""
    py = pm.languages.get("python", 0)
    ts = pm.languages.get("typescript", 0) + pm.languages.get("javascript", 0)
    return "python" if py >= ts else "typescript"


def _extract_scenario_id(body: str) -> str | None:
    marker = "Scenario: "
    idx = body.find(marker)
    if idx == -1:
        return None
    rest = body[idx + len(marker) :]
    end = min((rest.find(c) for c in (".", "\"", "*") if rest.find(c) != -1), default=-1)
    return rest[:end].strip() if end > 0 else rest.split()[0].strip()
