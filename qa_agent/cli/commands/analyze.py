"""`qa-agent analyze` — full Phase 1 pipeline.

Runs filesystem scan -> tech-stack detection -> dependency graph ->
API scan -> UI scan -> knowledge-graph build, and persists every result
through the StateManager.
"""

from __future__ import annotations

import argparse

from ...context.kg_builder import build_knowledge_graph
from ...scanners.api_scanner import scan_api
from ...scanners.dependency import build_dependency_graph
from ...scanners.filesystem import scan_filesystem
from ...scanners.tech_stack import scan_tech_stack
from ...scanners.ui_scanner import scan_ui
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state.manager import StateManager

log = get_logger("qa_agent.analyze")


def run(args: argparse.Namespace) -> int:
    project = args.project
    root = project_root(project)
    log.info("analyze: project=%s", root)
    sm = StateManager(project)

    pm = scan_filesystem(project)
    pm = scan_tech_stack(project, pm)
    sm.save(pm)
    log.info("analyze: project_map saved (%d files, %d frameworks)", len(pm.files), len(pm.frameworks))

    dep = build_dependency_graph(project, pm)
    sm.save(dep)
    log.info("analyze: dependency_graph saved (%d modules)", len(dep.modules))

    api = scan_api(project, pm)
    ui = scan_ui(project, pm)
    log.info("analyze: api=%d routes, ui=%d pages", len(api.routes), len(ui.pages))

    kg = build_knowledge_graph(pm, dep, api, ui)
    sm.save(kg)
    log.info("analyze: knowledge_graph saved (%d modules, %d features)", len(kg.modules), len(kg.features))

    return 0
