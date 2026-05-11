#!/usr/bin/env python3
"""CLI wrapper around qa_skills.validators.validate_test_output.

Usage (single output object):
    cat agent_result.json | python skills/_shared/scripts/validate_test_output.py
    python skills/_shared/scripts/validate_test_output.py --json '{"agent": ...}'
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.validators import validate_test_output  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="validate_test_output")
    parser.add_argument("--json", help="Inline JSON. If absent, reads from stdin.")
    args = parser.parse_args()

    raw = args.json if args.json is not None else sys.stdin.read()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)

    errors = validate_test_output(obj)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}))
        sys.exit(2)
    print(json.dumps({"status": "pass"}))
