"""Flaky-test detection by re-running the suite 3× and intersecting failures.

Replaces the qa-flaky-detector LLM agent with a deterministic Python module.
The LLM has no role here: re-run, parse JSON, classify. Cause hypotheses come
from name/content heuristics, not inference.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

_BORDER = r"(?:^|[^A-Za-z0-9])"  # word-or-underscore boundary; matches in `test_concurrent_writes`

CAUSE_RULES = (
    (re.compile(_BORDER + r"(concurrent|race|parallel|simultaneous)", re.I), "race_or_shared_state"),
    (re.compile(_BORDER + r"(timeout|wait|delay|sleep|debounce|throttle)", re.I), "timing_dependent"),
    (re.compile(r"(Date\.now|random|uuid|Math\.random|time\.time)", re.I), "non_deterministic_input"),
    (re.compile(_BORDER + r"(fetch|axios|requests\.(get|post)|httpx|http_client|external_api)", re.I), "external_dependency"),
    (re.compile(_BORDER + r"(setTimeout|setInterval|asyncio\.sleep)", re.I), "real_timer_used"),
)

CAUSE_HINTS = {
    "race_or_shared_state": "race_condition_or_shared_state",
    "timing_dependent":     "timing_dependent_assertion",
    "non_deterministic_input": "non_deterministic_input",
    "external_dependency":  "external_dependency_flakiness",
    "real_timer_used":      "timer_flakiness",
    "unknown":              "non_deterministic_unknown",
}

FIX_HINTS_EN = {
    "race_or_shared_state": "Reset shared state in beforeEach/setUp. Avoid module-level mutables.",
    "timing_dependent":     "Replace fixed waits with explicit conditions: waitFor / pollUntil.",
    "non_deterministic_input": "Mock Math.random / Date.now / UUID generators.",
    "external_dependency":  "Mock the external service or skip the test in CI.",
    "real_timer_used":      "Use fake timers (jest.useFakeTimers / freezegun).",
    "unknown":              "Review for shared state, timing, randomness, or external calls.",
}

FIX_HINTS_HE = {
    "race_or_shared_state": "אפס מצב משותף ב-beforeEach/setUp. הימנע ממשתנים גלובליים.",
    "timing_dependent":     "החלף waits קבועים בתנאים מפורשים: waitFor / pollUntil.",
    "non_deterministic_input": "Mock על Math.random / Date.now / יוצרי UUID.",
    "external_dependency":  "Mock על שירות חיצוני או דלג על הבדיקה ב-CI.",
    "real_timer_used":      "השתמש ב-fake timers (jest.useFakeTimers / freezegun).",
    "unknown":               "סקור עבור מצב משותף, תזמון, אקראיות, או קריאות חיצוניות.",
}


def _run_suite(project_root: Path, language: str, run_index: int) -> dict[str, str]:
    """Run suite once. Return {test_id: outcome} where outcome ∈ {passed, failed, skipped}."""
    out_path = project_root / ".qa-skills" / f"flaky-{run_index}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if language == "python":
        cmd = ["pytest", "--tb=no", "-q", "--json-report",
               f"--json-report-file={out_path}"]
        try:
            subprocess.run(cmd, cwd=project_root, capture_output=True, timeout=900, check=False)
        except (subprocess.SubprocessError, OSError):
            return {}
        return _parse_pytest_json(out_path)

    # ts/js
    cmd = ["npx", "jest", "--json", f"--outputFile={out_path}"]
    try:
        subprocess.run(cmd, cwd=project_root, capture_output=True, timeout=900, check=False)
    except (subprocess.SubprocessError, OSError):
        return {}
    return _parse_jest_json(out_path)


def _parse_pytest_json(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for t in data.get("tests", []) or []:
        nid = t.get("nodeid")
        outcome = t.get("outcome", "unknown")
        if nid:
            out[nid] = outcome
    return out


def _parse_jest_json(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for tr in data.get("testResults", []) or []:
        suite = tr.get("name") or tr.get("testFilePath", "")
        for r in tr.get("assertionResults", []) or []:
            nid = f"{suite}::{r.get('fullName') or r.get('title','')}"
            status = r.get("status", "unknown")
            out[nid] = "passed" if status == "passed" else ("failed" if status == "failed" else status)
    return out


def _hypothesize(test_id: str, source_excerpt: str = "") -> str:
    blob = f"{test_id}\n{source_excerpt}"
    for r, code in CAUSE_RULES:
        if r.search(blob):
            return code
    return "unknown"


def detect_flaky(
    project_root: str | Path,
    language: str,
    runs: int = 3,
    locale: str = "en",
) -> dict[str, Any]:
    pr = Path(project_root)
    runs_data: list[dict[str, str]] = []
    for i in range(1, runs + 1):
        runs_data.append(_run_suite(pr, language, i))

    if not any(runs_data):
        return {"agent": "qa-flaky-detector", "status": "skipped:suite_unrunnable",
                "flaky_tests": [], "runs_completed": 0}

    all_ids = set().union(*(set(r.keys()) for r in runs_data))
    flaky = []
    fix_hints = FIX_HINTS_HE if locale == "he" else FIX_HINTS_EN

    for tid in sorted(all_ids):
        outcomes = [r.get(tid, "missing") for r in runs_data]
        passed = sum(1 for o in outcomes if o == "passed")
        failed = sum(1 for o in outcomes if o == "failed")
        if passed > 0 and failed > 0:
            cause = _hypothesize(tid)
            flaky.append({
                "id": tid,
                "outcomes": outcomes,
                "pass_rate": round(passed / runs, 2),
                "cause_hypothesis": CAUSE_HINTS[cause],
                "suggested_fix": fix_hints[cause],
            })

    status = "passed" if not flaky else "partial"
    return {
        "agent": "qa-flaky-detector",
        "status": status,
        "flaky_tests": flaky,
        "runs_completed": runs,
    }


__all__ = ["detect_flaky", "CAUSE_HINTS", "FIX_HINTS_EN", "FIX_HINTS_HE"]


# CLI wrapper: skills/_shared/scripts/flaky.py
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(prog="qa_skills.flaky")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--language", required=True, choices=("typescript", "javascript", "python"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--locale", default="en", choices=("he", "en"))
    args = parser.parse_args()

    result = detect_flaky(args.project_root, args.language, runs=args.runs, locale=args.locale)
    print(json.dumps(result, indent=2))
