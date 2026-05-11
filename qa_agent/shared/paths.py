"""Path helpers for qa_agent.

Resolves project root, runtime workspace, and plugin-internal asset paths.
The plugin install dir is exposed via ${CLAUDE_PLUGIN_ROOT}; when running
the CLI outside Claude Code, we fall back to walking up from this file.
"""

from __future__ import annotations

import os
from pathlib import Path


def plugin_root() -> Path:
    """Return the plugin root directory.

    Prefers $CLAUDE_PLUGIN_ROOT (set by Claude Code). Falls back to the
    parent of this package — used for local dev / direct CLI invocations.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env).resolve()
    # qa_agent/shared/paths.py -> parents[2] == repo root
    return Path(__file__).resolve().parents[2]


def project_root(project: str | os.PathLike[str] | None) -> Path:
    """Resolve the user's target project root.

    Used for scans, test generation, execution. `None` means cwd.
    """
    if project is None:
        return Path.cwd().resolve()
    return Path(project).expanduser().resolve()


def qa_data_dir(project: str | os.PathLike[str] | None) -> Path:
    """Return `<project>/.qa-agent/`, creating it if missing."""
    root = project_root(project) / ".qa-agent"
    root.mkdir(parents=True, exist_ok=True)
    return root


def state_dir(project: str | os.PathLike[str] | None) -> Path:
    """Return `<project>/.qa-agent/state/`, creating it if missing."""
    d = qa_data_dir(project) / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runs_dir(project: str | os.PathLike[str] | None) -> Path:
    """Return `<project>/.qa-agent/runs/`, creating it if missing."""
    d = qa_data_dir(project) / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_dir(project: str | os.PathLike[str] | None, run_id: str) -> Path:
    """Return the per-run artifact directory, creating it if missing."""
    d = runs_dir(project) / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def configs_dir() -> Path:
    """Return the plugin's bundled configs directory."""
    return plugin_root() / "configs"


def prompts_dir() -> Path:
    """Return the plugin's bundled prompt-template directory."""
    return plugin_root() / "prompts"


def templates_dir() -> Path:
    """Return the plugin's bundled test scaffolding template directory."""
    return plugin_root() / "templates"


def reports_template_dir() -> Path:
    """Return the plugin's bundled HTML report template directory."""
    return plugin_root() / "reports"
