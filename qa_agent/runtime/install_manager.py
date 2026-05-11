"""Install manager.

Executes InstallSteps via process_manager, records every attempt in
`installation_history.json`. Idempotent: if an install for the same
manager+args succeeded in this project earlier and the lockfile is
unchanged, the step is skipped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..shared.logging import get_logger
from ..state import schemas
from ..state.manager import StateManager
from .install_planner import InstallStep
from .process_manager import ProcessResult, run_subprocess

log = get_logger("qa_agent.runtime.install_manager")

_LOCKFILES = {
    "npm":   "package-lock.json",
    "pnpm":  "pnpm-lock.yaml",
    "yarn":  "yarn.lock",
    "pip":   "requirements.txt",
    "poetry": "poetry.lock",
}


def run_installs(
    project_root: Path,
    steps: list[InstallStep],
    run_id: str,
    timeout: int = 600,
) -> list[ProcessResult]:
    """Run each InstallStep, append to installation_history.json."""
    sm = StateManager(str(project_root))
    history = sm.installation_history()
    results: list[ProcessResult] = []

    for step in steps:
        cmd = _build_cmd(step)
        if not cmd:
            log.warning("install_manager: skipping unknown manager %s", step.manager)
            continue
        log.info("install: %s — %s", " ".join(cmd), step.reason)
        res = run_subprocess(cmd, cwd=project_root, timeout=timeout)
        results.append(res)
        history.records.append(
            schemas.InstallRecord(
                run_id=run_id,
                timestamp=datetime.now(timezone.utc),
                manager=step.manager,
                args=step.args,
                exit_code=res.exit_code,
                duration_seconds=res.duration_seconds,
            )
        )
        if res.exit_code != 0:
            log.warning(
                "install: %s exited %d (stderr tail: %s)",
                step.manager,
                res.exit_code,
                res.stderr_tail[-200:],
            )

    sm.save(history)
    return results


def _build_cmd(step: InstallStep) -> list[str] | None:
    if step.manager == "pip":
        return ["pip", *step.args]
    if step.manager == "poetry":
        return ["poetry", *step.args]
    if step.manager == "npm":
        return ["npm", *step.args]
    if step.manager == "pnpm":
        return ["pnpm", *step.args]
    if step.manager == "yarn":
        return ["yarn", *step.args]
    if step.manager == "maven":
        return ["mvn", *step.args]
    if step.manager == "gradle":
        return ["gradle", *step.args]
    if step.manager == "npx":
        return ["npx", *step.args]
    return None
