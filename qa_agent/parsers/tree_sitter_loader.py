"""Tree-sitter grammar loader.

Tree-sitter is optional — if it isn't installed, callers must fall back
to the bridge parsers (ts_morph for TS/JS, javalang or grammar regex for
Java). The loader is lazy and caches parsers by language.
"""

from __future__ import annotations

from typing import Any

from ..shared.logging import get_logger

log = get_logger("qa_agent.parsers.tree_sitter_loader")

_PARSER_CACHE: dict[str, Any] = {}
_AVAILABLE: bool | None = None


def is_available() -> bool:
    """Return True if tree-sitter is importable."""
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_languages  # noqa: F401
        _AVAILABLE = True
    except ImportError:
        log.debug("tree-sitter not installed; bridge parsers will be used")
        _AVAILABLE = False
    return _AVAILABLE


def get_parser(language: str) -> Any | None:
    """Return a cached tree-sitter parser for `language`, or None.

    `language` should be one of: python, javascript, typescript, tsx, java,
    go, ruby, rust. The function is intentionally non-throwing — callers
    handle the `None` case with their own fallback path.
    """
    if not is_available():
        return None
    if language in _PARSER_CACHE:
        return _PARSER_CACHE[language]
    try:
        from tree_sitter_languages import get_parser as _g

        parser = _g(language)
    except Exception as e:  # noqa: BLE001 — third-party API surface
        log.warning("tree-sitter parser for %s unavailable: %s", language, e)
        return None
    _PARSER_CACHE[language] = parser
    return parser
