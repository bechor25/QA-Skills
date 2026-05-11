"""Self-healing engine.

For each failing test, classify the failure, look up an allowed action
in the policy, and apply a *bounded* mutation. The engine never weakens
assertions or mutes failures — only does conservative, additive fixes
like inserting a `await page.waitForLoadState` before an assertion or
adding a missing dep to the install plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..shared.logging import get_logger
from .classifiers import classify_failure
from .policies import DEFAULT_POLICY, FixAction, Policy, pick_action

log = get_logger("qa_agent.healing.engine")


@dataclass(slots=True)
class HealAttempt:
    test_path: str
    failure_category: str
    action: FixAction
    applied: bool
    note: str = ""


def heal_failures(
    project_root: Path,
    failures: Iterable[tuple[str, str]],  # (test_path, log_text)
    policy: Policy = DEFAULT_POLICY,
) -> list[HealAttempt]:
    """Try to heal each failing test. Returns one HealAttempt per input."""
    attempts: list[HealAttempt] = []
    for test_path, log_text in failures:
        cat = classify_failure(log_text)
        action = pick_action(cat, policy)
        applied = False
        note = ""
        try:
            if action == "add-wait":
                applied = _inject_wait(project_root / test_path)
                note = "inserted explicit wait before first assertion"
            elif action == "increase-timeout":
                applied = _bump_timeout(project_root / test_path)
                note = "doubled test timeout"
            elif action == "install-missing-dep":
                note = "deferred to install_manager — engine emits action only"
            else:
                note = "manual fix required"
        except Exception as e:  # noqa: BLE001 — never crash the run on a heal failure
            log.warning("heal: %s on %s raised %s", action, test_path, e)
            note = f"heal raised: {e}"

        attempts.append(
            HealAttempt(
                test_path=test_path,
                failure_category=cat,
                action=action,
                applied=applied,
                note=note,
            )
        )
    return attempts


# ---- Concrete fix actions --------------------------------------------------

def _inject_wait(path: Path) -> bool:
    """Insert `await page.waitForLoadState('networkidle')` before the first
    `expect(` in a Playwright test. No-op for python/jest files.
    """
    if not path.exists() or path.suffix not in {".ts", ".tsx", ".js"}:
        return False
    src = path.read_text(encoding="utf-8")
    if "waitForLoadState" in src:
        return False  # already waited
    marker = "await expect("
    idx = src.find(marker)
    if idx == -1:
        return False
    head, tail = src[:idx], src[idx:]
    new = head + "await page.waitForLoadState('networkidle');\n  " + tail
    path.write_text(new, encoding="utf-8")
    return True


def _bump_timeout(path: Path) -> bool:
    """Double the most recent `timeout: <ms>` literal in a Playwright/jest test.
    Returns False if no timeout literal is found.
    """
    import re

    if not path.exists():
        return False
    src = path.read_text(encoding="utf-8")
    pattern = re.compile(r"timeout\s*:\s*(\d+)")
    last_match: re.Match | None = None
    for m in pattern.finditer(src):
        last_match = m
    if not last_match:
        return False
    current = int(last_match.group(1))
    new_val = current * 2
    new_src = src[: last_match.start(1)] + str(new_val) + src[last_match.end(1) :]
    path.write_text(new_src, encoding="utf-8")
    return True
