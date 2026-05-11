"""Strategy gates.

* `has_signal(category, analysis)` — does the project contain anything for
  this category? Pure source-only check.
* `decide_category(category, analysis, server_plan, reachable)` — combines
  `has_signal` with the server-reachability matrix for `ui`/`a11y` so the
  orchestrator's strategy phase reflects dispatch reality BEFORE any sub-agent
  is invoked. The matrix mirrors `reference/server-policy.md`:

  | reachable | start_allowed | start_command | decision                                       |
  |-----------|---------------|---------------|------------------------------------------------|
  | true      | (any)         | (any)         | run                                            |
  | false     | true          | non-empty     | run (orchestrator will spawn before dispatch)  |
  | false     | true          | empty/null    | skip:server_unreachable_no_start_command       |
  | false     | false         | (any)         | skip:server_unreachable_no_start_permission    |
"""

from __future__ import annotations

from typing import Optional

from .types import Analysis, ServerPlan


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


_SERVER_GATED = frozenset({"ui", "a11y"})


def decide_category(
    category: str,
    analysis: Analysis,
    server_plan: Optional[ServerPlan] = None,
    reachable: bool = False,
) -> tuple[bool, str]:
    """Combine `has_signal` with the server-reachability matrix.

    For non-server-gated categories the result is identical to `has_signal`.
    For `ui`/`a11y` the server matrix runs after the signal check.

    Returns (should_run, reason_code). reason_code is "" when should_run.
    """
    ok, reason = has_signal(category, analysis)
    if not ok:
        return (False, reason)
    if category not in _SERVER_GATED:
        return (True, "")
    if reachable:
        return (True, "")
    if server_plan is None:
        return (False, "server_unreachable_no_start_permission")
    if not server_plan.start_allowed:
        return (False, "server_unreachable_no_start_permission")
    if not server_plan.start_command:
        return (False, "server_unreachable_no_start_command")
    return (True, "")


__all__ = ["has_signal", "decide_category"]


# CLI wrapper: skills/_shared/scripts/strategy.py
if __name__ == "__main__":
    import argparse
    import json
    import sys

    from .analysis import load_analysis
    from .server import build_server_plan, is_reachable

    parser = argparse.ArgumentParser(prog="qa_skills.strategy")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument(
        "--with-server-gate",
        action="store_true",
        help="Apply server-reachability matrix for ui/a11y (decide_category).",
    )
    parser.add_argument(
        "--allow-start",
        action="store_true",
        help="Permit orchestrator to spawn start_command. Default off.",
    )
    args = parser.parse_args()

    a = load_analysis(args.analysis)
    if args.with_server_gate:
        plan = build_server_plan(a, allow_start_explicit=args.allow_start)
        reachable = bool(plan.url) and is_reachable(plan.url)
        ok, reason = decide_category(args.category, a, plan, reachable)
    else:
        ok, reason = has_signal(args.category, a)
    print(json.dumps({"category": args.category, "should_run": ok, "reason": reason}))
    sys.exit(0)
