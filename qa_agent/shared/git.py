"""Thin git wrappers used by scanners + retry engine.

Every function is best-effort: a missing or broken git repo never raises —
the caller gets an empty list / None and proceeds in non-incremental mode.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def is_git_repo(project: Path) -> bool:
    """Return True if `project` is inside a git work tree."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def changed_files(project: Path, base: str = "HEAD~1") -> list[str]:
    """Return repo-relative paths changed since `base`. Empty if unavailable."""
    if not is_git_repo(project):
        return []
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return []
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def file_change_frequency(project: Path, paths: list[str], window_days: int = 180) -> dict[str, int]:
    """Return commit-touch counts per path within the window.

    Used by the risk engine as a proxy for "this code changes a lot".
    """
    if not is_git_repo(project) or not paths:
        return {}
    since = f"--since={window_days}.days"
    out: dict[str, int] = {}
    for path in paths:
        try:
            r = subprocess.run(
                ["git", "log", since, "--pretty=format:%H", "--", path],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            continue
        if r.returncode != 0:
            continue
        out[path] = sum(1 for ln in r.stdout.splitlines() if ln.strip())
    return out


def current_sha(project: Path) -> str | None:
    """Return the current HEAD sha, or None."""
    if not is_git_repo(project):
        return None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None
