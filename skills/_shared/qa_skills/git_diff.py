"""Per-module diff classification using git.

Replaces the qa-git-diff-analyzer LLM agent. Pure deterministic — git + regex,
no LLM required. Updates analysis.json in-place by adding `diff_class` to each
module entry.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

DIFF_CLASS = ("signature_changed", "body_changed", "trivial", "unchanged", "unknown")

# Signature markers per language. Tuples of compiled regexes applied to added/removed lines.
_SIG_TS = (
    re.compile(r"function\s+\w+\s*\("),
    re.compile(r"class\s+\w+"),
    re.compile(r"^\s*(public|private|protected)?\s*(async\s+)?\w+\s*\([^)]*\)\s*[:{]"),
    re.compile(r"=>\s*\("),
)
_SIG_PY = (
    re.compile(r"^\s*(async\s+)?def\s+\w+\s*\("),
    re.compile(r"^\s*class\s+\w+"),
)
_ROUTE_DEC = (
    re.compile(r"@app\.route"),
    re.compile(r"@router\.(get|post|put|patch|delete|head|options)"),
    re.compile(r"@app\.(get|post|put|patch|delete|head|options)"),
    re.compile(r"app\.(get|post|put|patch|delete)\s*\("),
)


def _has_git(project_root: Path) -> bool:
    try:
        subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD~1"],
            capture_output=True, timeout=10, check=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _diff_for(project_root: Path, file_path: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--unified=0", "HEAD~1", "HEAD", "--", file_path],
            capture_output=True, timeout=10, text=True,
        )
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return None


def _changed_lines(diff: str) -> list[str]:
    """Strip diff metadata. Return only added/removed code lines (no leading +/- after strip)."""
    lines: list[str] = []
    for ln in diff.splitlines():
        if ln.startswith(("+++", "---", "@@", "diff ", "index ", "Binary ")):
            continue
        if ln.startswith(("+", "-")) and not ln[1:].startswith(("+", "-")):
            lines.append(ln[1:])
    return lines


def _is_trivial(lines: Iterable[str], language: str) -> bool:
    if not lines:
        return False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue   # whitespace only
        if language == "python":
            if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
                continue
        else:  # ts/js
            if s.startswith("//") or s.startswith("/*") or s.startswith("*"):
                continue
        # String-literal-only change: line is fully wrapped in quotes
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            continue
        return False
    return True


def _has_signature_change(lines: Iterable[str], language: str) -> bool:
    sigs = _SIG_PY if language == "python" else _SIG_TS
    for ln in lines:
        for r in sigs:
            if r.search(ln):
                return True
        for r in _ROUTE_DEC:
            if r.search(ln):
                return True
    return False


def classify_diff(diff: str | None, language: str) -> str:
    """Map a per-file diff to one of DIFF_CLASS."""
    if diff is None:
        return "unknown"
    if not diff.strip():
        return "unchanged"
    lines = _changed_lines(diff)
    if not lines:
        return "unchanged"
    if _has_signature_change(lines, language):
        return "signature_changed"
    if _is_trivial(lines, language):
        return "trivial"
    return "body_changed"


def update_analysis(analysis_path: str | Path, project_root: str | Path | None = None) -> dict:
    """Read analysis.json, add diff_class to every module, write back. Return summary."""
    p = Path(analysis_path)
    data = json.loads(p.read_text(encoding="utf-8"))

    pr = Path(project_root) if project_root else Path(data.get("project_root", "."))
    language = data.get("language", "python")
    git_ok = _has_git(pr)

    counts = {k: 0 for k in DIFF_CLASS}
    for m in data.get("modules", []) or []:
        if not git_ok:
            cls = "unknown"
        else:
            # `path` is the canonical field per analysis.schema.json. `file` is
            # tolerated as a transitional fallback for older state files only.
            module_path = m.get("path") or m.get("file") or ""
            diff = _diff_for(pr, module_path) if module_path else None
            cls = classify_diff(diff, language)
        m["diff_class"] = cls
        counts[cls] += 1

    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {
        "modules_total": sum(counts.values()),
        "by_diff_class": counts,
    }


__all__ = ["DIFF_CLASS", "classify_diff", "update_analysis"]


# CLI wrapper: skills/_shared/scripts/git_diff.py
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.git_diff")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()

    summary = update_analysis(args.analysis, args.project_root)
    print(json.dumps({
        "agent": "qa-git-diff-analyzer",
        "status": "completed",
        "summary": summary,
    }))
