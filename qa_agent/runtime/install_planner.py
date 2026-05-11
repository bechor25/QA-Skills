"""Install planner.

Given the project map + the set of generated test frameworks, decide
*what* needs to be installed and in *which* package manager. Output is
a list of `InstallStep` the install manager runs in order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..shared.logging import get_logger
from ..state import schemas

log = get_logger("qa_agent.runtime.install_planner")


@dataclass(slots=True)
class InstallStep:
    manager: str          # npm | pnpm | pip | poetry | maven | gradle
    args: list[str]
    reason: str


# Default packages required by category. The planner only schedules the
# install if the category was actually generated.
_NODE_TEST_DEPS: dict[str, list[str]] = {
    "playwright": ["@playwright/test"],
    "playwright-a11y": ["@axe-core/playwright"],
    "jest": ["jest", "@jest/globals", "supertest", "@types/supertest"],
}

_PY_TEST_DEPS: dict[str, list[str]] = {
    "pytest": ["pytest"],
}


def plan_installs(
    pm: schemas.ProjectMap,
    tests: schemas.GeneratedTests,
) -> list[InstallStep]:
    steps: list[InstallStep] = []
    frameworks_used = {t.framework for t in tests.entries}
    categories_used = {t.category for t in tests.entries}

    if "pytest" in frameworks_used:
        manager = _python_manager(pm)
        steps.append(
            InstallStep(
                manager=manager,
                args=_python_install_args(manager, _PY_TEST_DEPS["pytest"]),
                reason="pytest required by generated python tests",
            )
        )

    if "playwright" in frameworks_used or "jest" in frameworks_used:
        node_mgr = _node_manager(pm)
        if "jest" in frameworks_used:
            steps.append(
                InstallStep(
                    manager=node_mgr,
                    args=_node_install_args(node_mgr, _NODE_TEST_DEPS["jest"], dev=True),
                    reason="jest+supertest required by generated TS API tests",
                )
            )
        if "playwright" in frameworks_used:
            steps.append(
                InstallStep(
                    manager=node_mgr,
                    args=_node_install_args(node_mgr, _NODE_TEST_DEPS["playwright"], dev=True),
                    reason="playwright required by generated UI/perf tests",
                )
            )
            if "accessibility" in categories_used:
                steps.append(
                    InstallStep(
                        manager=node_mgr,
                        args=_node_install_args(node_mgr, _NODE_TEST_DEPS["playwright-a11y"], dev=True),
                        reason="@axe-core/playwright required by a11y tests",
                    )
                )
            # Browsers
            steps.append(
                InstallStep(
                    manager="npx",
                    args=["playwright", "install", "--with-deps", "chromium"],
                    reason="install Playwright Chromium browser",
                )
            )

    log.info("install_planner: %d step(s)", len(steps))
    return steps


def _python_manager(pm: schemas.ProjectMap) -> str:
    if "poetry" in pm.package_managers:
        return "poetry"
    return "pip"


def _node_manager(pm: schemas.ProjectMap) -> str:
    if "pnpm" in pm.package_managers:
        return "pnpm"
    if "yarn" in pm.package_managers:
        return "yarn"
    return "npm"


def _python_install_args(manager: str, pkgs: list[str]) -> list[str]:
    if manager == "poetry":
        return ["add", "--dev", *pkgs]
    return ["install", "--quiet", *pkgs]


def _node_install_args(manager: str, pkgs: list[str], *, dev: bool) -> list[str]:
    if manager == "pnpm":
        return ["add", "-D" if dev else "", *pkgs] if dev else ["add", *pkgs]
    if manager == "yarn":
        return ["add", "--dev" if dev else "", *pkgs] if dev else ["add", *pkgs]
    return ["install", "--save-dev" if dev else "--save", *pkgs]
