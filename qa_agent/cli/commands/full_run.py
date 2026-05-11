"""`qa-agent full-run` — end-to-end pipeline.

Implements phases 0-4: analyze -> scenarios -> generation -> install -> execute.
Reporting follows in Phase 6.
"""

from __future__ import annotations

import argparse

import json

from ...agent.execution_controller import execute_all
from ...flaky.detector import detect_flaky
from ...healing.engine import heal_failures
from ...quality.generation_loop import run_generation_loop
from ...quality.scenario_generator import build_baseline_scenarios
from ...report.builder import build_report_data
from ...report.renderer import render_html
from ...runtime.install_manager import run_installs
from ...runtime.install_planner import plan_installs
from ...runtime.workspace import new_workspace
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state.manager import StateManager
from . import analyze

log = get_logger("qa_agent.full_run")


def run(args: argparse.Namespace) -> int:
    rc = analyze.run(args)
    if rc != 0:
        return rc

    project = args.project
    root = project_root(project)
    sm = StateManager(project)
    ws = new_workspace(project)
    log.info("full-run: workspace=%s", ws.root)

    strategy = sm.strategy()
    scenarios = build_baseline_scenarios(strategy)
    sm.save(scenarios)
    log.info("full-run: scenarios saved (%d)", len(scenarios.entries))

    pm = sm.project_map()
    generated, critique = run_generation_loop(root, scenarios, pm)
    sm.save(generated)
    sm.save(critique)
    log.info("full-run: generated=%d critique_avg=%.1f", len(generated.entries), _avg([r.score for r in critique.results]))

    skip_exec = bool(getattr(args, "no_llm", False))  # use --no-llm as proxy for offline runs
    if skip_exec:
        log.info("full-run: --no-llm set; skipping install + execute phases")
        return 0

    steps = plan_installs(pm, generated)
    if steps:
        run_installs(root, steps, ws.run_id)

    results = execute_all(root, generated, ws.run_id)
    total = sum(r.passed + r.failed + r.skipped for r in results)
    failed = sum(r.failed for r in results)
    log.info("full-run: executed %d tests across %d groups; failed=%d", total, len(results), failed)

    # Self-heal: try to fix deterministic failures, then once more.
    if failed:
        failures = _collect_failure_logs(results)
        attempts = heal_failures(root, failures)
        applied = [a for a in attempts if a.applied]
        if applied:
            log.info("full-run: healing applied to %d test file(s) — re-executing", len(applied))
            results = execute_all(root, generated, ws.run_id)
            failed = sum(r.failed for r in results)

    # Flaky detection on whatever's still failing.
    history = sm.execution_history()
    flaky = detect_flaky(root, generated, history)
    sm.save(flaky)
    log.info("full-run: flaky=%d", len(flaky.entries))

    data = build_report_data(project)
    data_path = ws.root / "report-data.json"
    data_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    html_path = render_html(data, project, ws.run_id)
    log.info("full-run: report=%s (score=%d)", html_path, data["executive_summary"]["quality_score"])
    return 0  # report carries the verdict


def _collect_failure_logs(results) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for r in results:
        if r.failed <= 0 or r.process is None:
            continue
        text = (r.process.stderr_tail or "") + "\n" + (r.process.stdout_tail or "")
        for path in r.test_files:
            out.append((path, text))
    return out


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0
