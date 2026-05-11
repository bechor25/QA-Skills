"""Run-planner.

Decides which phases to execute for a given CLI invocation. The default
plan is the full sequence in `Phase.ordered()`; flags like `--no-llm`
or `--scope failed` reduce it.

This is intentionally pure data — no side effects — so the CLI driver
can dry-run a plan to show the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lifecycle import Phase


@dataclass(slots=True)
class RunPlan:
    phases: list[Phase] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def plan_full_run(no_llm: bool = False) -> RunPlan:
    plan = RunPlan(phases=list(Phase.ordered()))
    if no_llm:
        keep = {
            Phase.SCAN, Phase.TECH_STACK, Phase.DEPENDENCY, Phase.API_SCAN,
            Phase.UI_SCAN, Phase.KNOWLEDGE_GRAPH, Phase.RISK, Phase.STRATEGY,
            Phase.SCENARIOS, Phase.GENERATE, Phase.CRITIC, Phase.REPORT,
        }
        plan.phases = [p for p in plan.phases if p in keep]
        plan.notes.append("--no-llm: skipping install + execute + heal + flaky")
    return plan


def plan_analyze() -> RunPlan:
    return RunPlan(
        phases=[
            Phase.SCAN, Phase.TECH_STACK, Phase.DEPENDENCY, Phase.API_SCAN,
            Phase.UI_SCAN, Phase.KNOWLEDGE_GRAPH, Phase.RISK, Phase.STRATEGY,
        ],
        notes=["analyze-only: no scenarios/generation/execution"],
    )


def plan_rerun(scope: str) -> RunPlan:
    return RunPlan(
        phases=[Phase.EXECUTE, Phase.REPORT],
        notes=[f"rerun scope={scope}"],
    )
