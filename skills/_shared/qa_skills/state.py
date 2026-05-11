"""test-state.json read/write/diff.

Shape (project_root/test-state.json):
{
  "run_id": "uuid",
  "generated_at": "ISO_TIMESTAMP",
  "modules": [
    {"name": "app.auth", "file": "app/auth.py", "hash": "sha256...",
     "test_paths": ["tests/unit/auth/test_auth.py", ...],
     "execution_result": "passed|failed|partial"}
  ]
}

Note: legacy state files use `name`+`file`. We preserve those keys when carrying
unchanged modules across runs to avoid breaking incremental flow. New entries
written by `write_state` use `path` (canonical). Read helpers normalize both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import Analysis


def _module_id(entry: dict) -> str:
    """Normalized id for a state entry — prefer `path`, fall back to `file`."""
    return entry.get("path") or entry.get("file") or entry.get("name") or ""


def read_state(state_path: str | Path) -> dict[str, Any] | None:
    p = Path(state_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def diff_modules(prior_state: dict | None, analysis: Analysis) -> dict[str, list[str]]:
    """Return {changed: [...], new: [...], unchanged: [...]} of module paths."""
    prior_by_id: dict[str, dict] = {}
    if prior_state and isinstance(prior_state.get("modules"), list):
        for m in prior_state["modules"]:
            mid = _module_id(m)
            if mid:
                prior_by_id[mid] = m

    changed: list[str] = []
    new: list[str] = []
    unchanged: list[str] = []
    for m in analysis.modules:
        prev = prior_by_id.get(m.path)
        if prev is None:
            new.append(m.path)
        elif prev.get("hash") != m.hash:
            changed.append(m.path)
        else:
            unchanged.append(m.path)
    return {"changed": changed, "new": new, "unchanged": unchanged}


def write_state(
    state_path: str | Path,
    *,
    run_id: str,
    generated_at: str,
    analysis: Analysis,
    test_paths_by_module: dict[str, list[str]],
    execution_result_by_module: dict[str, str],
    prior_state: dict | None = None,
) -> dict:
    """Build + write test-state.json.

    Carries over unchanged modules from prior state. New/changed modules get fresh
    hashes + test paths from the current run.
    """
    by_id_prior: dict[str, dict] = {}
    if prior_state and isinstance(prior_state.get("modules"), list):
        for m in prior_state["modules"]:
            mid = _module_id(m)
            if mid:
                by_id_prior[mid] = m

    out_modules: list[dict] = []
    for m in analysis.modules:
        prev = by_id_prior.get(m.path)
        if prev and prev.get("hash") == m.hash:
            entry = dict(prev)  # carry over (preserves legacy `name`/`file` if present)
            entry["path"] = m.path
            entry["hash"] = m.hash
        else:
            entry = {
                "path": m.path,
                "hash": m.hash,
                "test_paths": test_paths_by_module.get(m.path, []),
                "execution_result": execution_result_by_module.get(m.path, "unknown"),
            }
        out_modules.append(entry)

    state = {
        "run_id": run_id,
        "generated_at": generated_at,
        "modules": out_modules,
    }
    Path(state_path).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


__all__ = ["read_state", "write_state", "diff_modules"]
