#!/usr/bin/env python3
"""CLI wrapper around qa_skills.validators.validate_agent_result_against_contract.

Used by orchestrator Phase 3 post-dispatch (Track A2 hard policy):
  * `extras`     — emitted paths NOT in expected_files (wrong-named). Delete + warn.
  * `missing`    — expected paths not emitted. Add to coverage[cat].missing_items[].
  * `violations` — emitted paths failing language-aware regex (A4). Warn.

Usage:
    cat agent_result.json | python skills/_shared/scripts/contract_diff.py \
        --expected-files .qa-skills/logs/<run_id>/expected_files.json \
        --category api \
        --language typescript
    # or inline:
    python skills/_shared/scripts/contract_diff.py \
        --result '{"agent":"qa-api-test","status":"passed","outputs":[...]}' \
        --expected-files .qa-skills/logs/<run_id>/expected_files.json \
        --category api --language typescript

Exit codes:
    0  — no extras, no missing, no violations.
    1  — extras OR missing OR violations present (orchestrator must act).
    2  — input/parse error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.validators import validate_agent_result_against_contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="contract_diff")
    parser.add_argument("--result", help="Inline AgentResult JSON. If absent, read stdin.")
    parser.add_argument(
        "--expected-files",
        required=True,
        help="Path to ${LOGS_DIR}/expected_files.json (full map of all categories).",
    )
    parser.add_argument(
        "--category",
        required=True,
        help="One of: unit | api | ui | security | a11y | contract",
    )
    parser.add_argument(
        "--language",
        required=True,
        help="Project language: python | typescript | javascript.",
    )
    args = parser.parse_args()

    raw = args.result if args.result is not None else sys.stdin.read()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL: bad agent result JSON: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    ef_path = Path(args.expected_files)
    if not ef_path.is_file():
        print(f"FAIL: expected_files not found: {ef_path}", file=sys.stderr)
        return 2
    try:
        ef_map = json.loads(ef_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: bad expected_files JSON: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    expected = ef_map.get(args.category)
    if not isinstance(expected, list):
        print(
            f"FAIL: expected_files['{args.category}'] not a list",
            file=sys.stderr,
        )
        return 2

    diff = validate_agent_result_against_contract(
        result, expected_files=expected, language=args.language,
    )

    payload = {
        "agent": result.get("agent"),
        "category": args.category,
        "language": args.language,
        "extras":     diff["extras"],
        "missing":    diff["missing"],
        "violations": diff["violations"],
    }
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")

    if diff["extras"] or diff["missing"] or diff["violations"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
