#!/usr/bin/env python3
"""CLI wrapper around qa_skills.analysis.

Usage:
    python skills/_shared/scripts/validate_analysis.py --analysis path/to/analysis.json [--strict]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis, AnalysisValidationError  # noqa: E402

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="validate_analysis")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    try:
        a = load_analysis(args.analysis, strip_forbidden=not args.strict)
    except AnalysisValidationError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(2)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)

    summary = {
        "language": a.language,
        "modules": len(a.modules),
        "routes": len(a.routes),
        "api_routes": sum(1 for _ in a.api_routes()),
        "page_routes": sum(1 for _ in a.page_routes()),
        "frontend_files": len(a.frontend_files),
        "frontend_kind": a.frontend_kind,
    }
    print(json.dumps(summary))
