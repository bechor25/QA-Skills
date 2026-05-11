"""has_signal — does this category have anything to test in this project?"""

from __future__ import annotations

from .types import Analysis


def has_signal(category: str, analysis: Analysis) -> tuple[bool, str]:
    """Return (should_run, reason_code).

    `reason_code` is the closed-enum code that goes into categories_skipped[*].reason
    when the bool is False. See `reference/category-boundaries.md` for the closed list.
    """
    has_fe = bool(analysis.stats.get("has_frontend"))
    fe_kind = analysis.frontend_kind

    if category == "unit":
        if any(m.type != "frontend" for m in analysis.modules):
            return (True, "")
        return (False, "no_non_frontend_modules")

    if category in ("api", "contract"):
        if any(True for _ in analysis.api_routes()):
            return (True, "")
        return (False, "no_routes_detected")

    if category == "ui":
        if not has_fe:
            return (False, "no_frontend_detected")
        if fe_kind == "none":
            return (False, "frontend_kind_none")
        if fe_kind not in ("spa", "ssr", "mixed"):
            return (False, f"unsupported_frontend_kind:{fe_kind}")
        return (True, "")

    if category == "a11y":
        if not has_fe:
            return (False, "no_frontend_detected")
        if fe_kind == "none":
            return (False, "frontend_kind_none")
        return (True, "")

    if category == "security":
        if any(m.has_auth or m.has_db_queries or m.input_fields for m in analysis.modules):
            return (True, "")
        return (False, "no_auth_db_or_input_signals")

    return (False, f"unknown_category:{category}")


__all__ = ["has_signal"]


# CLI wrapper: skills/_shared/scripts/strategy.py
if __name__ == "__main__":
    import argparse
    import json
    import sys

    from .analysis import load_analysis

    parser = argparse.ArgumentParser(prog="qa_skills.strategy")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--category", required=True)
    args = parser.parse_args()

    a = load_analysis(args.analysis)
    ok, reason = has_signal(args.category, a)
    print(json.dumps({"category": args.category, "should_run": ok, "reason": reason}))
    sys.exit(0)
