#!/usr/bin/env python3
"""CLI wrapper around qa_skills.state.write_state.

Usage:
    python skills/_shared/scripts/state_write.py --inputs inputs.json --out test-state.json

inputs.json shape:
    {
      "analysis_path": "/abs/path/analysis.json",
      "run_id": "uuid",
      "generated_at": "ISO_TIMESTAMP",
      "test_paths_by_module":      {"app/auth.py": ["tests/unit/auth/test_auth.py", ...], ...},
      "execution_result_by_module": {"app/auth.py": "passed", ...},
      "prior_state_path": "/abs/path/test-state.json"   (optional)
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.analysis import load_analysis  # noqa: E402
from qa_skills.state import read_state, write_state  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="state_write")
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    analysis = load_analysis(inputs["analysis_path"])
    prior = read_state(inputs["prior_state_path"]) if inputs.get("prior_state_path") else None

    state = write_state(
        args.out,
        run_id=inputs["run_id"],
        generated_at=inputs["generated_at"],
        analysis=analysis,
        test_paths_by_module=inputs.get("test_paths_by_module", {}),
        execution_result_by_module=inputs.get("execution_result_by_module", {}),
        prior_state=prior,
    )
    print(json.dumps({
        "status": "completed",
        "state_path": args.out,
        "modules": len(state.get("modules", [])),
    }))
