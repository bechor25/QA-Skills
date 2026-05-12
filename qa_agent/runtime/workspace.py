"""Per-run workspace under `<project>/.qa-agent/runs/<run_id>/`.

The workspace owns: logs, captured artifacts (screenshots/videos),
per-run checkpoints, and the path that the report renderer reads from.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..shared.paths import run_dir, runs_dir


@dataclass(slots=True)
class Workspace:
    run_id: str
    root: Path
    logs: Path
    artifacts: Path
    started_at: datetime


def new_workspace(project: str | Path | None = None) -> Workspace:
    run_id = _make_run_id()
    root = run_dir(project, run_id)
    logs = root / "logs"
    arts = root / "artifacts"
    logs.mkdir(parents=True, exist_ok=True)
    arts.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    (root / "run.json").write_text(
        json.dumps({"run_id": run_id, "started_at": started.isoformat()}, indent=2),
        encoding="utf-8",
    )
    return Workspace(run_id=run_id, root=root, logs=logs, artifacts=arts, started_at=started)


def latest_run(project: str | Path | None = None) -> Workspace | None:
    base = runs_dir(project)
    entries = [p for p in base.iterdir() if p.is_dir()]
    if not entries:
        return None
    # IDs are time-prefixed, so lexicographic order works.
    latest = max(entries, key=lambda p: p.name)
    info_path = latest / "run.json"
    if info_path.exists():
        meta = json.loads(info_path.read_text(encoding="utf-8"))
        try:
            started = datetime.fromisoformat(meta["started_at"])
        except (KeyError, ValueError):
            started = datetime.now(timezone.utc)
    else:
        started = datetime.now(timezone.utc)
    return Workspace(
        run_id=latest.name,
        root=latest,
        logs=latest / "logs",
        artifacts=latest / "artifacts",
        started_at=started,
    )


def _make_run_id() -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{now}-{uuid.uuid4().hex[:6]}"


def latest_run_id(project: str | Path | None = None) -> str | None:
    ws = latest_run(project)
    return ws.run_id if ws else None
