"""Atomic JSON IO with pydantic round-trip support.

Writes go to <path>.tmp then rename — readers never see a half-written file.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import StateError


def read_json(path: str | os.PathLike[str]) -> Any:
    """Read JSON from `path`. Raises StateError if missing or invalid."""
    p = Path(path)
    if not p.exists():
        raise StateError(f"state file missing: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise StateError(f"state file corrupt: {p}: {e}") from e


def read_json_or(path: str | os.PathLike[str], default: Any) -> Any:
    """Read JSON from `path`, or return `default` if the file is missing."""
    p = Path(path)
    if not p.exists():
        return default
    return read_json(p)


def write_json(path: str | os.PathLike[str], data: Any) -> None:
    """Atomically write `data` to `path` as pretty-printed JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(
        prefix=p.name + ".",
        suffix=".tmp",
        dir=str(p.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(serialized)
            tmp.write("\n")
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
