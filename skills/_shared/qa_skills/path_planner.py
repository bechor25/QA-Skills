"""compute_expected_files — sole authority for `tests/<category>/...` layout.

Mirrors the logic previously inlined in `qa-orchestrator.md` Phase 2.5. The
orchestrator invokes via wrapper script `skills/_shared/scripts/plan_expected_files.py`.
Sub-agents must NOT call this — they receive the slice for their category as
`expected_files` inside the path_contract input.
"""

from __future__ import annotations

from .routes import derive_domain_and_tag, is_api_route
from .types import Analysis, ExpectedFile

DROP_SOURCE_DIRS: frozenset[str] = frozenset({
    "src", "app", "lib", "pkg", "internal", "cmd", "__init__", "tests",
})

SKIP_FRONTEND_STEMS: frozenset[str] = frozenset({
    "_base", "base", "layout", "__init__",
})


def _python_test_filename(stem: str, suffix: str) -> str:
    return f"test_{stem}{suffix}.py"


def _ts_test_filename(stem: str, suffix: str) -> str:
    return f"{stem}{suffix}.ts"


def _testname(stem: str, suffix_py: str, suffix_ts: str, *, is_python: bool) -> str:
    return _python_test_filename(stem, suffix_py) if is_python else _ts_test_filename(stem, suffix_ts)


def _api_like(category: str, analysis: Analysis, language: str) -> list[ExpectedFile]:
    """api / contract / security all group routes by (domain, tag)."""
    suffixes = {
        "api":      ("",          ".api.test"),
        "contract": ("",          ".contract.test"),
        "security": ("_security", ".security.test"),
    }
    sfx_py, sfx_ts = suffixes[category]
    is_py = language == "python"

    pairs: dict[tuple[str, str], list[str]] = {}
    for r in analysis.api_routes():
        pairs.setdefault(derive_domain_and_tag(r.path), []).append(r.covers_id)

    result = []
    for (domain, tag), covers in sorted(pairs.items()):
        fname = _testname(tag, sfx_py, sfx_ts, is_python=is_py)
        result.append(ExpectedFile(
            path=f"tests/{category}/{domain}/{fname}",
            covers=tuple(sorted(covers)),
        ))
    return result


def _frontend_pages(category: str, analysis: Analysis, language: str) -> list[ExpectedFile]:
    """ui / a11y — one file per page (template / SPA route)."""
    is_py = language == "python"
    sfx_ts = ".spec" if category == "ui" else ".a11y.spec"

    pages: list[tuple[str, str]] = []
    seen: set[str] = set()
    for f in analysis.page_files():
        stem = f.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if stem in SKIP_FRONTEND_STEMS or stem in seen:
            continue
        seen.add(stem)
        pages.append((stem, f.path))

    return [
        ExpectedFile(
            path=f"tests/{category}/{stem}/{_testname(stem, '', sfx_ts, is_python=is_py)}",
            covers=(src,),
        )
        for stem, src in pages
    ]


def _unit(analysis: Analysis, language: str) -> list[ExpectedFile]:
    """unit — one file per non-frontend module, mirrored under tests/unit/<domain>/."""
    is_py = language == "python"
    files: list[ExpectedFile] = []
    for m in analysis.non_frontend_modules():
        seg = [s for s in m.path.replace("\\", "/").split("/")
               if s and s not in DROP_SOURCE_DIRS]
        if not seg:
            short, domain = "root", "root"
        elif len(seg) == 1:
            short = seg[-1].rsplit(".", 1)[0]
            domain = short
        else:
            short = seg[-1].rsplit(".", 1)[0]
            domain = seg[-2]
        files.append(ExpectedFile(
            path=f"tests/unit/{domain}/{_testname(short, '', '.test', is_python=is_py)}",
            covers=(m.path,),
        ))
    return files


def compute_expected_files(category: str, analysis: Analysis, language: str) -> list[ExpectedFile]:
    """Return the ordered, deduplicated list of test files for a category.

    `language` is one of LANGUAGE; we currently encode python vs ts/js layout.
    """
    if category in ("api", "contract", "security"):
        return _api_like(category, analysis, language)
    if category in ("ui", "a11y"):
        return _frontend_pages(category, analysis, language)
    if category == "unit":
        return _unit(analysis, language)
    return []


__all__ = ["compute_expected_files", "DROP_SOURCE_DIRS", "SKIP_FRONTEND_STEMS"]


# CLI wrapper: skills/_shared/scripts/plan_expected_files.py
if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.path_planner")
    parser.add_argument("--analysis", required=True, help="Path to analysis.json")
    parser.add_argument("--category", required=True, choices=("unit", "api", "ui", "security", "a11y", "contract"))
    args = parser.parse_args()

    with open(args.analysis, encoding="utf-8") as f:
        analysis = Analysis.from_dict(json.load(f))

    files = compute_expected_files(args.category, analysis, analysis.language)
    json.dump([ef.to_dict() for ef in files], sys.stdout, indent=2)
    sys.stdout.write("\n")
