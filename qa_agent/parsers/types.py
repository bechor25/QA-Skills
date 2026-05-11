"""Common parser output types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SymbolKind = Literal[
    "function",
    "class",
    "method",
    "route",
    "component",
    "decorator",
    "import",
]


@dataclass(slots=True)
class Symbol:
    name: str
    kind: SymbolKind
    line: int | None = None
    parent: str | None = None
    decorators: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedFile:
    path: str
    language: str
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    routes: list[Symbol] = field(default_factory=list)  # subset of symbols
    parse_error: str | None = None
