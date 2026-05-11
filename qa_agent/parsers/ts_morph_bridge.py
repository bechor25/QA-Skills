"""Bridge to a Node helper for TypeScript/JavaScript parsing.

Tries ts-morph first; falls back to a regex extractor inside the helper.
If `node` itself is unavailable we degrade gracefully to a pure-regex
Python implementation so the QA Agent never hard-requires Node.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ..shared.logging import get_logger
from ..shared.paths import plugin_root
from .types import ParsedFile, Symbol

log = get_logger("qa_agent.parsers.ts_morph_bridge")

_NODE_AVAILABLE: bool | None = None


def _node_path() -> str | None:
    return shutil.which("node")


def has_node() -> bool:
    global _NODE_AVAILABLE
    if _NODE_AVAILABLE is None:
        _NODE_AVAILABLE = _node_path() is not None
    return _NODE_AVAILABLE


def parse_ts_files(project_root: Path, rel_paths: list[str]) -> list[ParsedFile]:
    """Parse a batch of TS/JS files. Returns one ParsedFile per input path."""
    if not rel_paths:
        return []

    if has_node():
        try:
            return _parse_via_node(project_root, rel_paths)
        except Exception as e:  # noqa: BLE001 — fall back rather than fail the whole scan
            log.warning("ts_morph bridge failed (%s); falling back to regex", e)

    return [_regex_parse(project_root, rel) for rel in rel_paths]


def _parse_via_node(project_root: Path, rel_paths: list[str]) -> list[ParsedFile]:
    script = plugin_root() / "qa_agent" / "parsers" / "_node" / "ts_morph_extract.js"
    if not script.exists():
        raise FileNotFoundError(f"node helper missing: {script}")
    payload = json.dumps({"root": str(project_root), "paths": rel_paths})
    r = subprocess.run(
        [_node_path() or "node", str(script)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node helper exited {r.returncode}: {r.stderr.strip()[:400]}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"node helper produced invalid JSON: {e}") from e
    if data.get("error"):
        raise RuntimeError(data["error"])

    out: list[ParsedFile] = []
    for raw in data.get("files", []):
        pf = ParsedFile(
            path=raw["path"],
            language=raw.get("language", "typescript"),
            imports=raw.get("imports", []) or [],
        )
        for s in raw.get("symbols", []) or []:
            pf.symbols.append(
                Symbol(
                    name=s.get("name", "<anonymous>"),
                    kind=s.get("kind", "function"),
                    line=s.get("line"),
                    parent=s.get("parent"),
                )
            )
        for r_ in raw.get("routes", []) or []:
            pf.routes.append(
                Symbol(name=r_.get("name", ""), kind="route", line=r_.get("line"))
            )
        if raw.get("parse_error"):
            pf.parse_error = raw["parse_error"]
        out.append(pf)
    return out


# ---- Pure-Python fallback ----------------------------------------------------

_IMPORT_RE = re.compile(r"""^\s*import\s+(?:[^'"]+from\s+)?["']([^"']+)["']""", re.MULTILINE)
_FUNC_RE = re.compile(r"""^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(""", re.MULTILINE)
_CLASS_RE = re.compile(r"""^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z0-9_]+)""", re.MULTILINE)
_ARROW_RE = re.compile(
    r"""^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*(?::\s*[^=]+)?=\s*(?:async\s*)?\(.*?\)\s*=>""",
    re.MULTILINE,
)
_ROUTE_RE = re.compile(
    r"""(?:app|router|server)\s*\.\s*(get|post|put|patch|delete|all|use|route)\s*\(\s*["'`]([^"'`]+)["'`]""",
    re.IGNORECASE,
)


def _regex_parse(project_root: Path, rel: str) -> ParsedFile:
    abs_path = project_root / rel
    language = "typescript" if rel.endswith((".ts", ".tsx")) else "javascript"
    pf = ParsedFile(path=rel, language=language)
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        pf.parse_error = f"read failed: {e}"
        return pf

    pf.imports = _IMPORT_RE.findall(text)

    def _line(start: int) -> int:
        return text.count("\n", 0, start) + 1

    for m in _FUNC_RE.finditer(text):
        pf.symbols.append(Symbol(name=m.group(1), kind="function", line=_line(m.start())))
    for m in _CLASS_RE.finditer(text):
        pf.symbols.append(Symbol(name=m.group(1), kind="class", line=_line(m.start())))
    for m in _ARROW_RE.finditer(text):
        pf.symbols.append(Symbol(name=m.group(1), kind="function", line=_line(m.start())))
    for m in _ROUTE_RE.finditer(text):
        pf.routes.append(
            Symbol(
                name=f"{m.group(1).upper()} {m.group(2)}",
                kind="route",
                line=_line(m.start()),
            )
        )

    return pf
