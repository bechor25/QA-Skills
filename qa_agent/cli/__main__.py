"""qa-agent CLI entry point.

Invoked by:
  - the `qa-master` Claude Code agent (via skill triggers)
  - users directly: `python -m qa_agent.cli ...` or `qa-agent ...`

Subcommands are thin shells that delegate to qa_agent.cli.commands.*; each
command takes a parsed argparse namespace, runs its phase, and exits with
0 on success or a non-zero code on hard failure.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .. import __version__
from ..shared.logging import get_logger
from .commands import (
    analyze,
    build_strategy,
    full_run,
    prepare,
    probe_select,
    rerun,
    report,
    retry_decide,
    run_tests,
    scaffold,
    state,
)

log = get_logger("qa_agent.cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qa-agent",
        description="QA Operating System — scan, plan, generate, run, report.",
    )
    parser.add_argument("--version", action="version", version=f"qa-agent {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_full = sub.add_parser("full-run", help="Scan, plan, generate, execute, report.")
    p_full.add_argument("--project", default=None)
    p_full.add_argument("--categories", default=None, help="Comma-separated subset.")
    p_full.add_argument("--no-llm", action="store_true", help="Run non-LLM phases only.")
    p_full.set_defaults(func=full_run.run)

    p_analyze = sub.add_parser("analyze", help="Scan and build the knowledge graph only.")
    p_analyze.add_argument("--project", default=None)
    p_analyze.set_defaults(func=analyze.run)

    p_prep = sub.add_parser(
        "prepare",
        help="Phases 1-3: analyze + UI selectors + test-data plan. "
             "After it returns, qa-master fans out qa-enricher per capability.",
    )
    p_prep.add_argument("--project", default=None)
    p_prep.set_defaults(func=prepare.run)

    p_bs = sub.add_parser(
        "build-strategy",
        help="Rebuild strategy.json from the refined capability_map.json "
             "(falls back to raw_capability_map.json or the legacy risk-matrix path).",
    )
    p_bs.add_argument("--project", default=None)
    p_bs.set_defaults(func=build_strategy.run)

    p_scaf = sub.add_parser(
        "scaffold",
        help="Phase 6: emit scaffolded test files (it.todo stubs) from scenarios shards.",
    )
    p_scaf.add_argument("--project", default=None)
    p_scaf.add_argument(
        "--probe-only",
        action="store_true",
        dest="probe_only",
        help="Emit only probe-tagged scenarios under tests/qa-agent/_probe/.",
    )
    p_scaf.set_defaults(func=scaffold.run)

    p_run = sub.add_parser(
        "run-tests",
        help="Phase 8: execute the generated suite. Skip install with --skip-install.",
    )
    p_run.add_argument("--project", default=None)
    p_run.add_argument("--skip-install", action="store_true")
    p_run.add_argument("--timeout", type=int, default=300)
    p_run.add_argument(
        "--probe-only",
        action="store_true",
        dest="probe_only",
        help="Run only the Phase 3.5 probe tests (under tests/qa-agent/_probe/).",
    )
    p_run.set_defaults(func=run_tests.run)

    p_probe = sub.add_parser(
        "probe-select",
        help="Phase 3.5 gate: read probe_analysis.json + probe_report.md, "
             "prompt the operator for each suggested override, write user_overrides.json.",
    )
    p_probe.add_argument("--project", default=None)
    p_probe.add_argument(
        "--non-interactive",
        action="store_true",
        dest="non_interactive",
        help="Accept every suggested override without prompting.",
    )
    p_probe.set_defaults(func=probe_select.run)

    p_dec = sub.add_parser(
        "retry-decide",
        help="Emit JSON retry decisions after triage. Used by qa-master to "
             "know which failing tests to re-run.",
    )
    p_dec.add_argument("--project", default=None)
    p_dec.set_defaults(func=retry_decide.run)

    p_rerun = sub.add_parser("rerun", help="Re-execute a previously generated suite.")
    p_rerun.add_argument("--project", default=None)
    p_rerun.add_argument(
        "--scope",
        choices=["flaky", "changed", "failed", "all"],
        default="changed",
    )
    p_rerun.set_defaults(func=rerun.run)

    p_report = sub.add_parser("report", help="Render the latest HTML report.")
    p_report.add_argument("--project", default=None)
    p_report.add_argument("--open", action="store_true", dest="open_browser")
    p_report.set_defaults(func=report.run)

    p_state = sub.add_parser("state", help="Inspect or reset state.")
    p_state.add_argument("--project", default=None)
    p_state.add_argument("action", choices=["show", "reset"])
    p_state.set_defaults(func=state.run)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130
    except Exception:  # noqa: BLE001
        log.exception("qa-agent failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
