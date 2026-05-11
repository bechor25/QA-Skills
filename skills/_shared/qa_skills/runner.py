"""Test execution + canonical result parsing (Track C3).

Detects the test runner from `analysis.json` + category, spawns it, parses
runner-native JSON into a stable shape, and returns the structured result.

Hard contract — the same shape regardless of runner:

```
{
  "category":   "api",
  "runner":     "vitest" | "jest" | "pytest" | "playwright",
  "total":      int,
  "passed":     int,
  "failed":     int,
  "skipped":    int,
  "duration_ms": int,
  "failures": [
    {"file": str, "title": str, "error": str, "stack_excerpt": str}
  ],
  "exit_code":  int
}
```

Sub-agents call the CLI wrapper before returning AgentResult — orchestrator
rejects `status: passed` without a verified execution_result attached.

Stdlib only. Never installs runners. If the project's runner is not present
on disk, returns `runner_missing` and `exit_code=127`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

# ---------- runner selection ----------

_VITEST_HINTS = ("vitest.config.ts", "vitest.config.js", "vitest.config.mjs")
_JEST_HINTS   = ("jest.config.ts", "jest.config.js", "jest.config.cjs", "jest.config.mjs")
_PLAYWRIGHT_HINTS = ("playwright.config.ts", "playwright.config.js")
_PYTEST_HINTS = ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")

# UI/a11y always runs through Playwright when the project ships its config.
_FRONTEND_CATEGORIES = frozenset({"ui", "a11y"})


def detect_runner(project_root: Path, language: str, category: str) -> str:
    """Return one of: vitest | jest | pytest | playwright | unknown."""
    pr = Path(project_root)

    if category in _FRONTEND_CATEGORIES:
        if any((pr / h).is_file() for h in _PLAYWRIGHT_HINTS):
            return "playwright"
        # Frontend category but no playwright config → cannot execute.
        return "unknown"

    if language == "python":
        if any((pr / h).is_file() for h in _PYTEST_HINTS):
            return "pytest"
        # `pytest` may still be installed without a config; default to it.
        return "pytest"

    # ts/js — prefer vitest over jest if both present (vitest is faster).
    if any((pr / h).is_file() for h in _VITEST_HINTS):
        return "vitest"
    if any((pr / h).is_file() for h in _JEST_HINTS):
        return "jest"
    # `package.json` projects without an explicit config still often use vitest.
    pkg = pr / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        deps = {
            **(data.get("dependencies") or {}),
            **(data.get("devDependencies") or {}),
        }
        if "vitest" in deps:
            return "vitest"
        if "jest" in deps:
            return "jest"
    return "unknown"


def _resolve_files_from_agent_output(agent_output_json: dict | list) -> list[str]:
    """Accept either a merged AgentResult dict or a {files:[...]} dict."""
    if isinstance(agent_output_json, list):
        return [p for p in agent_output_json if isinstance(p, str)]
    if not isinstance(agent_output_json, dict):
        return []
    if isinstance(agent_output_json.get("files"), list):
        return [p for p in agent_output_json["files"] if isinstance(p, str)]
    paths: list[str] = []
    for o in agent_output_json.get("outputs", []) or []:
        if isinstance(o, dict) and isinstance(o.get("path"), str):
            paths.append(o["path"])
    return paths


# ---------- parsers ----------


def _parse_vitest(stdout: str, exit_code: int) -> dict[str, Any]:
    """Vitest --reporter=json emits a JSON object on stdout."""
    data = _json_blob(stdout)
    total = passed = failed = skipped = 0
    failures: list[dict[str, str]] = []
    duration_ms = 0

    if isinstance(data, dict):
        total = int(data.get("numTotalTests") or 0)
        passed = int(data.get("numPassedTests") or 0)
        failed = int(data.get("numFailedTests") or 0)
        skipped = int(data.get("numPendingTests") or 0) + int(data.get("numTodoTests") or 0)
        duration_ms = int(data.get("startTime", 0) and (data.get("endTime") or data["startTime"]) - data["startTime"]) or 0
        for tr in data.get("testResults") or []:
            fpath = tr.get("name") or tr.get("testFilePath") or ""
            for r in tr.get("assertionResults") or []:
                if r.get("status") == "failed":
                    msgs = r.get("failureMessages") or []
                    msg = (msgs[0] if msgs else "").strip()
                    failures.append({
                        "file": fpath,
                        "title": r.get("fullName") or r.get("title") or "",
                        "error": _first_line(msg),
                        "stack_excerpt": _excerpt(msg, 10),
                    })

    return {
        "runner": "vitest",
        "total": total, "passed": passed, "failed": failed, "skipped": skipped,
        "duration_ms": duration_ms,
        "failures": failures,
        "exit_code": exit_code,
    }


def _parse_jest(stdout: str, exit_code: int) -> dict[str, Any]:
    # Jest --json shape is nearly identical to vitest; reuse parser.
    parsed = _parse_vitest(stdout, exit_code)
    parsed["runner"] = "jest"
    return parsed


def _parse_pytest(json_report_path: Path, exit_code: int) -> dict[str, Any]:
    if not json_report_path.is_file():
        return {
            "runner": "pytest", "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "duration_ms": 0, "failures": [], "exit_code": exit_code,
        }
    try:
        data = json.loads(json_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "runner": "pytest", "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "duration_ms": 0, "failures": [], "exit_code": exit_code,
        }

    summary = data.get("summary", {}) or {}
    total   = int(summary.get("total") or 0)
    passed  = int(summary.get("passed") or 0)
    failed  = int(summary.get("failed") or 0) + int(summary.get("error") or 0)
    skipped = int(summary.get("skipped") or 0)
    duration_ms = int((data.get("duration") or 0) * 1000)

    failures: list[dict[str, str]] = []
    for t in data.get("tests") or []:
        if t.get("outcome") in ("failed", "error"):
            call = t.get("call") or {}
            longrepr = call.get("longrepr") or t.get("longrepr") or ""
            failures.append({
                "file": (t.get("nodeid") or "").split("::", 1)[0],
                "title": (t.get("nodeid") or "").split("::", 1)[-1],
                "error": _first_line(str(longrepr)),
                "stack_excerpt": _excerpt(str(longrepr), 10),
            })
    return {
        "runner": "pytest",
        "total": total, "passed": passed, "failed": failed, "skipped": skipped,
        "duration_ms": duration_ms,
        "failures": failures,
        "exit_code": exit_code,
    }


def _parse_playwright(json_report_path: Path, exit_code: int) -> dict[str, Any]:
    if not json_report_path.is_file():
        return {
            "runner": "playwright", "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "duration_ms": 0, "failures": [], "exit_code": exit_code,
        }
    try:
        data = json.loads(json_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "runner": "playwright", "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "duration_ms": 0, "failures": [], "exit_code": exit_code,
        }

    total = passed = failed = skipped = 0
    duration_ms = int(data.get("stats", {}).get("duration") or 0)
    failures: list[dict[str, str]] = []

    def _walk(suite: dict, file_path: str = "") -> None:
        nonlocal total, passed, failed, skipped
        fpath = suite.get("file") or file_path
        for spec in suite.get("specs") or []:
            for t in spec.get("tests") or []:
                total += 1
                results = t.get("results") or []
                statuses = [r.get("status") for r in results]
                if "passed" in statuses:
                    passed += 1
                elif "failed" in statuses or "timedOut" in statuses:
                    failed += 1
                    last = results[-1] if results else {}
                    err = last.get("error", {}) or {}
                    failures.append({
                        "file": fpath,
                        "title": spec.get("title") or "",
                        "error": _first_line(err.get("message") or ""),
                        "stack_excerpt": _excerpt(err.get("stack") or "", 10),
                    })
                elif "skipped" in statuses:
                    skipped += 1
        for child in suite.get("suites") or []:
            _walk(child, fpath)

    for s in data.get("suites") or []:
        _walk(s)

    return {
        "runner": "playwright",
        "total": total, "passed": passed, "failed": failed, "skipped": skipped,
        "duration_ms": duration_ms,
        "failures": failures,
        "exit_code": exit_code,
    }


# ---------- runners ----------


def run_tests(
    category: str,
    project_root: str | Path,
    files: Iterable[str],
    language: str,
    timeout_seconds: int = 600,
    runner: str | None = None,
) -> dict[str, Any]:
    """Run the test runner against `files` and return canonical result."""
    pr = Path(project_root)
    file_list = sorted({p for p in files if isinstance(p, str) and p})
    rname = runner or detect_runner(pr, language, category)

    if rname == "unknown":
        return _empty(category, "unknown", exit_code=127,
                      note="runner_unknown_no_config_detected")
    if not file_list:
        return _empty(category, rname, exit_code=0,
                      note="no_files_to_run")

    if rname == "vitest":
        result = _exec_vitest(pr, file_list, timeout_seconds)
    elif rname == "jest":
        result = _exec_jest(pr, file_list, timeout_seconds)
    elif rname == "pytest":
        result = _exec_pytest(pr, file_list, timeout_seconds)
    elif rname == "playwright":
        result = _exec_playwright(pr, file_list, timeout_seconds)
    else:
        return _empty(category, rname, exit_code=127,
                      note=f"runner_not_implemented:{rname}")

    result["category"] = category
    return result


# ---------- exec helpers ----------


def _exec_vitest(pr: Path, files: list[str], timeout: int) -> dict[str, Any]:
    if not shutil.which("npx"):
        return _missing_tool("vitest", "npx not found")
    cmd = ["npx", "--no-install", "vitest", "run", "--reporter=json"] + files
    return _run_node(cmd, pr, timeout, _parse_vitest)


def _exec_jest(pr: Path, files: list[str], timeout: int) -> dict[str, Any]:
    if not shutil.which("npx"):
        return _missing_tool("jest", "npx not found")
    cmd = ["npx", "--no-install", "jest", "--json"] + files
    return _run_node(cmd, pr, timeout, _parse_jest)


def _exec_pytest(pr: Path, files: list[str], timeout: int) -> dict[str, Any]:
    if not shutil.which("pytest") and not shutil.which("python3"):
        return _missing_tool("pytest", "neither pytest nor python3 on PATH")
    json_report = pr / ".qa-skills" / "exec-pytest.json"
    json_report.parent.mkdir(parents=True, exist_ok=True)
    runner_cmd = ["pytest"] if shutil.which("pytest") else ["python3", "-m", "pytest"]
    cmd = runner_cmd + ["--tb=short", "-q",
                        "--json-report", f"--json-report-file={json_report}"] + files
    try:
        proc = subprocess.run(  # noqa: S603 — files validated upstream
            cmd, cwd=pr, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _empty("", "pytest", exit_code=124, note="timeout")
    except OSError as e:
        return _empty("", "pytest", exit_code=127, note=f"exec_failed:{e}")
    return _parse_pytest(json_report, proc.returncode)


def _exec_playwright(pr: Path, files: list[str], timeout: int) -> dict[str, Any]:
    if not shutil.which("npx"):
        return _missing_tool("playwright", "npx not found")
    json_report = pr / ".qa-skills" / "exec-playwright.json"
    json_report.parent.mkdir(parents=True, exist_ok=True)
    env_str = f"PLAYWRIGHT_JSON_OUTPUT_NAME={json_report}"
    cmd = ["npx", "--no-install", "playwright", "test",
           "--reporter=json"] + files
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, cwd=pr, capture_output=True, text=True, timeout=timeout,
            env={**__import_env(), "PLAYWRIGHT_JSON_OUTPUT_NAME": str(json_report)},
        )
    except subprocess.TimeoutExpired:
        return _empty("", "playwright", exit_code=124, note="timeout")
    except OSError as e:
        return _empty("", "playwright", exit_code=127, note=f"exec_failed:{e}")
    # Playwright writes to file when PLAYWRIGHT_JSON_OUTPUT_NAME is set;
    # falls back to stdout if not.
    if json_report.is_file():
        return _parse_playwright(json_report, proc.returncode)
    # Try parsing stdout blob.
    parsed = _json_blob(proc.stdout)
    if isinstance(parsed, dict):
        json_report.write_text(json.dumps(parsed), encoding="utf-8")
        return _parse_playwright(json_report, proc.returncode)
    return _empty("", "playwright", exit_code=proc.returncode,
                  note=f"unparseable_output:{env_str}")


def _run_node(cmd: list[str], pr: Path, timeout: int, parser) -> dict[str, Any]:
    try:
        proc = subprocess.run(  # noqa: S603 — validated
            cmd, cwd=pr, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _empty("", cmd[2], exit_code=124, note="timeout")
    except OSError as e:
        return _empty("", cmd[2], exit_code=127, note=f"exec_failed:{e}")
    return parser(proc.stdout, proc.returncode)


def __import_env() -> dict[str, str]:
    import os
    return dict(os.environ)


# ---------- small utils ----------


def _json_blob(text: str):
    """Extract last balanced JSON object/array from runner stdout."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find last `{`-`}` block by scanning braces.
    starts = [i for i, ch in enumerate(text) if ch in "{["]
    for start in reversed(starts):
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _first_line(s: str) -> str:
    if not s:
        return ""
    return s.splitlines()[0].strip()[:240]


def _excerpt(s: str, n_lines: int) -> str:
    if not s:
        return ""
    return "\n".join(s.splitlines()[:n_lines])[:1024]


def _empty(category: str, runner: str, *, exit_code: int, note: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {
        "category": category,
        "runner": runner,
        "total": 0, "passed": 0, "failed": 0, "skipped": 0,
        "duration_ms": 0, "failures": [],
        "exit_code": exit_code,
    }
    if note:
        out["note"] = note
    return out


def _missing_tool(runner: str, reason: str) -> dict[str, Any]:
    return _empty("", runner, exit_code=127, note=f"runner_missing:{reason}")


__all__ = ["detect_runner", "run_tests"]


# CLI wrapper: skills/_shared/scripts/run_tests.py
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.runner")
    parser.add_argument("--category", required=True,
                        choices=("unit", "api", "ui", "security", "a11y", "contract"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument(
        "--files-json",
        required=True,
        help="Path to AgentResult JSON (or [path,...]). Use '-' for stdin.",
    )
    parser.add_argument("--out", required=False)
    parser.add_argument("--runner", required=False,
                        choices=("vitest", "jest", "pytest", "playwright"))
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    if args.files_json == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.files_json).read_text(encoding="utf-8")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL: bad files JSON: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)

    files = _resolve_files_from_agent_output(obj)
    result = run_tests(
        category=args.category,
        project_root=args.project_root,
        files=files,
        language=args.language,
        runner=args.runner,
        timeout_seconds=args.timeout,
    )
    out_str = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_str, encoding="utf-8")
    print(out_str)
    sys.exit(0 if result.get("exit_code", 1) == 0 else 1)
