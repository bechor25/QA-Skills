"""``qa-agent probe-select`` — present the Phase 3.5 probe questions
to the operator and persist their confirmed answers as
``state/user_overrides.json``.

The qa-probe-analyzer sub-agent has already written:

  * ``state/probe_report.md`` — operator-facing question list
    (Hebrew by default, every question numbered and given a
    default answer).
  * ``state/probe_analysis.json`` — machine-readable verdict per
    probe scenario, plus a ``suggested_override`` payload keyed by
    capability for the schema-mismatch / auth-flow-unknown
    verdicts.

This command:

  1. Prints the probe report so the operator can read every
     question and its proposed default.
  2. Walks the suggested_override payloads on stdin, accepting
     ``y`` / ``n`` / free-text per question.
  3. Merges all confirmed overrides into a single
     ``state/user_overrides.json`` file keyed by capability.

No project-specific values are baked in; everything is sourced
from ``probe_analysis.json`` which the analyzer wrote based on
real probe-run logs.

A ``--non-interactive`` flag accepts every suggested default (used
by CI and integration tests).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ...shared.logging import get_logger
from ...shared.paths import project_root

log = get_logger("qa_agent.probe_select")


def run(args: argparse.Namespace) -> int:
    project = args.project
    root = project_root(project)
    state_dir = Path(root) / ".qa-agent" / "state"
    analysis_path = state_dir / "probe_analysis.json"
    report_path = state_dir / "probe_report.md"
    overrides_path = state_dir / "user_overrides.json"

    if not analysis_path.exists():
        log.warning(
            "probe-select: %s missing — run the probe gate first "
            "(scenarios with probe_mode=true → scaffold --probe-only → "
            "run-tests --probe-only → qa-probe-analyzer).",
            analysis_path,
        )
        return 1

    analysis = _load_json(analysis_path)
    verdicts = analysis.get("verdicts") or []
    actionable = [v for v in verdicts if v.get("suggested_override")]

    if report_path.exists():
        sys.stdout.write("\n" + report_path.read_text(encoding="utf-8") + "\n")

    if not actionable:
        log.info("probe-select: no overrides suggested — writing empty user_overrides.json")
        _write_overrides(overrides_path, {})
        return 0

    overrides: dict[str, dict] = {}
    non_interactive = bool(getattr(args, "non_interactive", False))

    for v in actionable:
        cap = v.get("capability") or ""
        suggested = v.get("suggested_override") or {}
        if not cap or not suggested:
            continue
        if non_interactive:
            decision = "y"
            note = ""
        else:
            decision, note = _ask(v)
        if decision == "y":
            entry = overrides.setdefault(cap, {})
            entry.update(suggested)
            if note:
                entry["notes"] = (entry.get("notes", "") + (" " + note if entry.get("notes") else note)).strip()

    _write_overrides(overrides_path, overrides)
    log.info(
        "probe-select: wrote %d capability overrides to %s",
        len(overrides),
        overrides_path,
    )
    return 0


def _ask(verdict: dict) -> tuple[str, str]:
    """Prompt for confirmation. Returns (decision, optional_note).

    decision == "y" → apply suggested override
    decision == "n" → skip; note ignored
    """
    qid = verdict.get("operator_question_id", "?")
    cap = verdict.get("capability", "?")
    cat = verdict.get("category", "?")
    sys.stdout.write(
        f"\n[{qid}] capability={cap} category={cat} — apply suggested override? "
        "([y]/n, or type 'n: <reason>' to skip with a note): "
    )
    sys.stdout.flush()
    try:
        raw = sys.stdin.readline().strip()
    except (KeyboardInterrupt, EOFError):
        return "n", "operator aborted"
    if not raw:
        return "y", ""
    lowered = raw.lower()
    if lowered.startswith("y"):
        return "y", raw[1:].strip(": ").strip()
    if lowered.startswith("n"):
        return "n", raw[1:].strip(": ").strip()
    return "y", raw


def _write_overrides(path: Path, overrides: dict[str, dict]) -> None:
    payload = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "_decisions": "applied" if overrides else "no overrides applied",
        **overrides,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("probe-select: failed to load %s: %s", path, e)
        return {}
