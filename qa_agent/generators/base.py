"""Shared helpers for test generators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class GeneratedFile:
    """One file emitted by a generator."""

    rel_path: str          # path relative to project root
    body: str
    framework: str
    language: str


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, default: str = "scenario") -> str:
    """Lowercase, dash-separated slug suitable for filenames."""
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or default


def write_file(project_root: Path, gf: GeneratedFile) -> Path:
    """Write a generated file under the project root, creating parents."""
    abs_path = project_root / gf.rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(gf.body, encoding="utf-8")
    return abs_path
