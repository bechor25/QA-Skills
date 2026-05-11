"""StateManager round-trip tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from qa_agent.state import schemas
from qa_agent.state.manager import StateManager


def test_state_round_trip_default_when_missing(tmp_path: Path):
    sm = StateManager(tmp_path)
    pm = sm.project_map()
    assert pm.schema_version == 1
    assert pm.files == []


def test_state_save_and_reload(tmp_path: Path):
    sm = StateManager(tmp_path)
    pm = schemas.ProjectMap(
        project_root=str(tmp_path),
        scanned_at=datetime.now(timezone.utc),
        languages={"python": 3},
        files=[schemas.FileEntry(path="a.py", language="python", size_bytes=10)],
    )
    sm.save(pm)
    reloaded = sm.project_map()
    assert reloaded.languages == {"python": 3}
    assert reloaded.files[0].path == "a.py"


def test_atomic_write_does_not_leak_tmp(tmp_path: Path):
    sm = StateManager(tmp_path)
    sm.save(schemas.FlakyState())
    leftovers = list(sm.dir.glob("*.tmp"))
    assert leftovers == []
