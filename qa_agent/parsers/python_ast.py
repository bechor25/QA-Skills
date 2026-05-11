"""Python AST parser — pure stdlib.

Extracts top-level + nested symbols and recognizes framework decorators
(FastAPI/Flask/Django) as route definitions.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..shared.logging import get_logger
from .types import ParsedFile, Symbol

log = get_logger("qa_agent.parsers.python_ast")


# Decorator name patterns that mark a function as a route. We match on
# the last attribute (e.g. `app.get` matches `get`).
_ROUTE_DECORATORS: set[str] = {
    "get", "post", "put", "patch", "delete", "head", "options",
    "route",            # flask/quart
    "api_view",         # DRF
    "websocket",
}


def parse_python_file(project_root: Path, rel_path: str) -> ParsedFile:
    """Parse `<project_root>/<rel_path>` and return a ParsedFile."""
    abspath = project_root / rel_path
    pf = ParsedFile(path=rel_path, language="python")
    try:
        source = abspath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        pf.parse_error = f"read failed: {e}"
        return pf

    try:
        tree = ast.parse(source, filename=str(abspath))
    except SyntaxError as e:
        pf.parse_error = f"syntax error: {e.msg} at line {e.lineno}"
        return pf

    for node in ast.iter_child_nodes(tree):
        _visit_top_level(node, pf)

    return pf


def _visit_top_level(node: ast.AST, pf: ParsedFile) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            pf.imports.append(alias.name)
        return
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            pf.imports.append(f"{module}.{alias.name}" if module else alias.name)
        return
    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
        sym = _make_func_symbol(node, parent=None)
        pf.symbols.append(sym)
        if _is_route(sym):
            sym.kind = "route"
            pf.routes.append(sym)
        return
    if isinstance(node, ast.ClassDef):
        cls = Symbol(name=node.name, kind="class", line=node.lineno)
        cls.decorators = [_decorator_repr(d) for d in node.decorator_list]
        pf.symbols.append(cls)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = _make_func_symbol(item, parent=node.name)
                method.kind = "method"
                pf.symbols.append(method)
                if _is_route(method):
                    method.kind = "route"
                    pf.routes.append(method)


def _make_func_symbol(node: ast.FunctionDef | ast.AsyncFunctionDef, parent: str | None) -> Symbol:
    return Symbol(
        name=node.name,
        kind="function",
        line=node.lineno,
        parent=parent,
        decorators=[_decorator_repr(d) for d in node.decorator_list],
    )


def _decorator_repr(d: ast.expr) -> str:
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Attribute):
        return f"{_decorator_repr(d.value)}.{d.attr}" if isinstance(d.value, (ast.Name, ast.Attribute)) else d.attr
    if isinstance(d, ast.Call):
        return _decorator_repr(d.func)
    return ast.unparse(d) if hasattr(ast, "unparse") else d.__class__.__name__


def _is_route(sym: Symbol) -> bool:
    for deco in sym.decorators:
        last = deco.rsplit(".", 1)[-1].lower()
        if last in _ROUTE_DECORATORS:
            return True
    return False
