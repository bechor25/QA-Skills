"""Import-path validator.

Static check: every relative `import ... from "./..."` and
`import "..."` statement in a generated test file must resolve to an
existing file on disk. Catches broken-shim cases like the original
`import app from "../../../src/server"` when no such file exists.

Only relative imports are checked — bare-package imports
(`supertest`, `@jest/globals`, ...) are assumed to be handled by the
install planner.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..state import schemas

_IMPORT_RES: list[re.Pattern[str]] = [
    # `import x from "./y"` / `import { a } from "../y"`
    re.compile(r"""^\s*import\s+[^'"]+?\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE),
    # `import "./y"`
    re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.MULTILINE),
    # CommonJS: `require("./y")`
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    # Python: `from .y import x`, `import x.y`
    re.compile(r"""^\s*from\s+([\.\w]+)\s+import\s+""", re.MULTILINE),
]

_NODE_EXTS = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".d.ts")


def validate_imports(test_path: Path) -> list[schemas.CritiqueFinding]:
    """Return one `import-unresolved` finding per unresolved relative import.

    Bare module specifiers (no leading `.` or `/`) are ignored.
    """
    try:
        text = test_path.read_text(encoding="utf-8")
    except OSError as e:
        return [schemas.CritiqueFinding(rule="read-failed", severity="error", message=str(e))]

    findings: list[schemas.CritiqueFinding] = []
    seen: set[str] = set()
    for pat in _IMPORT_RES:
        for match in pat.finditer(text):
            spec = match.group(1)
            if spec in seen:
                continue
            seen.add(spec)
            if not _is_relative(spec):
                continue
            if _resolves(test_path.parent, spec):
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                schemas.CritiqueFinding(
                    rule="import-unresolved",
                    severity="error",
                    message=f"unresolved import: '{spec}'",
                    line=line,
                )
            )
    return findings


def _is_relative(spec: str) -> bool:
    return spec.startswith(("./", "../", "/"))


def _resolves(base_dir: Path, spec: str) -> bool:
    """True if `spec` resolves to an existing file relative to `base_dir`.

    Handles common Node module resolution: exact file, file with TS/JS
    extension, or `index.{ts,js}` inside a directory.
    """
    target = (base_dir / spec).resolve()
    if target.is_file():
        return True
    for ext in _NODE_EXTS:
        if target.with_suffix(ext).is_file():
            return True
        if Path(str(target) + ext).is_file():
            return True
    if target.is_dir():
        for ext in _NODE_EXTS:
            if (target / f"index{ext}").is_file():
                return True
    return False
