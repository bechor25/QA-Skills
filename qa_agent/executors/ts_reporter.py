"""Shared parsing helpers for jest- and vitest-style JSON reporters.

Both runners produce nearly identical JSON output shapes when called
with ``--json`` (jest) or ``--reporter=json`` (vitest):

  {
    "testResults": [
      {
        "name": "<absolute path>",
        "assertionResults": [
          {"title": "...", "status": "passed|failed|pending|...",
           "failureMessages": ["..."], "duration": 12}
        ]
      }
    ],
    "numPassedTests": N, "numFailedTests": N, "numPendingTests": N
  }

This module owns that parser so JestRunner and VitestRunner stay
short and identical in behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import PerTestRecord, extract_scenario_id


def parse_jest_style_json_file(
    report_path: Path,
    project_root: Path,
    fallback_stdout: str = "",
) -> tuple[int, int, int, list[PerTestRecord]]:
    """Same shape as ``parse_jest_style_json`` but reads the JSON from
    ``report_path`` written via ``--outputFile`` / ``--reporter=json``.

    Falls back to ``fallback_stdout`` when the file is missing or
    empty (e.g. runner crashed before writing).
    """
    text = ""
    try:
        if report_path.exists():
            text = report_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if not text:
        text = fallback_stdout
    return parse_jest_style_json(text, project_root)


def parse_jest_style_json(
    stdout: str,
    project_root: Path,
) -> tuple[int, int, int, list[PerTestRecord]]:
    """Return ``(passed, failed, skipped, per_test_records)``.

    Tolerates leading non-JSON noise (banners, deprecation warnings)
    by scanning for the first ``{`` that opens a parseable object.
    """
    blob = _find_json_object(stdout)
    if blob is None:
        return 0, 0, 0, []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return 0, 0, 0, []

    passed = int(data.get("numPassedTests", 0))
    failed = int(data.get("numFailedTests", 0))
    skipped = int(data.get("numPendingTests", 0)) + int(data.get("numTodoTests", 0))

    records: list[PerTestRecord] = []
    for tr in data.get("testResults", []) or []:
        file_abs = tr.get("name") or tr.get("testFilePath") or ""
        file_rel = _rel_path(file_abs, project_root)
        for ar in tr.get("assertionResults", []) or []:
            title = ar.get("title") or ar.get("fullName") or ""
            status = _normalize_status(ar.get("status", "unknown"))
            duration = float(ar.get("duration") or 0.0)
            messages = ar.get("failureMessages") or []
            err_msg = ""
            err_stack = ""
            if messages:
                # Jest puts the assertion message + stack in one string
                # per failure. First line is usually the message, the
                # rest is the stack.
                first = str(messages[0])
                lines = first.split("\n", 1)
                err_msg = lines[0]
                err_stack = lines[1] if len(lines) > 1 else ""
            scenario_id = extract_scenario_id(title) or extract_scenario_id(ar.get("fullName") or "")
            test_id = scenario_id or f"{file_rel}::{title}"
            records.append(
                PerTestRecord(
                    test_id=test_id,
                    file=file_rel,
                    title=title,
                    status=status,
                    duration_ms=duration,
                    error_message=err_msg,
                    error_stack=err_stack,
                )
            )

    # When the runner crashes during setup, jest/vitest emit a top-level
    # error per file. Surface that as a single failed record so triage
    # has something to read.
    if not records:
        for tr in data.get("testResults", []) or []:
            msg = tr.get("message") or tr.get("failureMessage") or ""
            if not msg:
                continue
            file_rel = _rel_path(tr.get("name") or "", project_root)
            records.append(
                PerTestRecord(
                    test_id=f"{file_rel}::__file__",
                    file=file_rel,
                    title="(file-level error)",
                    status="failed",
                    error_message=msg.split("\n", 1)[0],
                    error_stack=msg,
                )
            )

    return passed, failed, skipped, records


def _find_json_object(text: str) -> str | None:
    """Locate the first balanced JSON object in ``text``. Walks
    bracket depth to find the matching close, so leading log lines
    won't break the parse.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        # malformed — try the next opening brace
        start = text.find("{", start + 1)
    return None


def _rel_path(absolute: str, project_root: Path) -> str:
    if not absolute:
        return ""
    try:
        return str(Path(absolute).resolve().relative_to(project_root.resolve()))
    except (ValueError, OSError):
        return absolute


def _normalize_status(s: str) -> str:
    s = (s or "").lower()
    return {
        "passed": "passed",
        "failed": "failed",
        "pending": "skipped",
        "skipped": "skipped",
        "todo": "skipped",
        "disabled": "skipped",
    }.get(s, s or "other")
