"""Collect UI/a11y artifacts (Playwright reports, screenshots, videos, traces).

Replaces inline `collect_artifacts` from qa-coverage-reporter.md Phase 2.5.
Pure IO — no LLM, deterministic.
"""

from __future__ import annotations

from pathlib import Path

MAX_ARTIFACTS_PER_KIND = 50


def _validate_html(p: str | None, project_root: Path) -> str | None:
    """playwright_report / axe_report MUST point to an existing .html. Else None."""
    if not p:
        return None
    if not p.endswith(".html"):
        return None
    if not Path(p).is_file():
        return None
    return p


def _canonical_html(category: str, project_root: Path) -> str | None:
    if category == "ui":
        canonical = project_root / "tests" / "ui" / "playwright-report" / "index.html"
    else:
        canonical = project_root / "tests" / "a11y" / "axe-report" / "index.html"
    return str(canonical) if canonical.is_file() else None


def collect_artifacts(
    agent_output: dict,
    category: str,
    project_root: str | Path,
) -> dict | None:
    """Walk artifacts_dir, classify files, return top-level artifacts block.

    Returns None when category is not ui/a11y or agent_output is None.
    """
    if not agent_output or category not in ("ui", "a11y"):
        return None

    pr = Path(project_root)
    raw = agent_output.get("html_report")
    validated = _validate_html(raw, pr) or _canonical_html(category, pr)

    art: dict = {
        ("playwright_report" if category == "ui" else "axe_report"): validated,
        "test_results_dir": agent_output.get("artifacts_dir"),
        "screenshots": [],
        "videos": [],
        "traces": [],
    }

    results_dir = agent_output.get("artifacts_dir")
    if results_dir and Path(results_dir).is_dir():
        rd = Path(results_dir)
        for p in rd.rglob("*"):
            if not p.is_file():
                continue
            try:
                rel = str(p.relative_to(pr))
            except ValueError:
                rel = str(p)
            name = p.name.lower()
            if name.endswith((".png", ".jpg", ".jpeg")):
                art["screenshots"].append(rel)
            elif name.endswith((".webm", ".mp4")):
                art["videos"].append(rel)
            elif name.endswith(".zip") and "trace" in name:
                art["traces"].append(rel)
        for k in ("screenshots", "videos", "traces"):
            art[k] = sorted(art[k])[:MAX_ARTIFACTS_PER_KIND]

    return art


__all__ = ["collect_artifacts", "MAX_ARTIFACTS_PER_KIND"]
