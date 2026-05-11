#!/usr/bin/env python3
"""QA-Skills v2 driver — top-level pipeline runner.

Replaces the LLM-driven `qa-orchestrator` agent. The driver owns phase
sequencing, verification, execution, and reporting. LLM sub-agents are
invoked via `qa_skills.driver.task_subprocess` only for bounded per-file
work.

Step A scope (this file at present):
  Phase 0 — setup directories + run_id
  Phase 1 — scan (qa-code-analyzer + analysis.json verification)
  Phase 2 — strategy (plan_expected_files + server_plan + decide_category)

Later steps add Phase 2.7 (domain learn), Phase 3 (dispatch), 5/5.5/6/7/8/9.

Usage:
    python3 scripts/qa_run.py --project-root /abs/path [--locale en]
                              [--mode auto] [--categories unit,api]
                              [--force-full] [--interactive]

Exit codes:
    0  — Phase 2 reached. JSON summary on stdout.
    1  — Setup error (project_root unreadable, dir creation failed).
    2  — Phase 1 error (analyzer failed or analysis.json invalid).
    3  — Phase 2 error (path planner or strategy failed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Allow `from qa_skills...` imports when invoked directly from scripts/.
_SHARED_DIR = Path(__file__).resolve().parent.parent
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from qa_skills.analysis import (  # noqa: E402
    AnalysisValidationError,
    load_analysis,
)
from qa_skills.driver import (  # noqa: E402
    TaskCall,
    TaskError,
    atomic_write_json,
    build_run_context,
    now_iso,
    phase_checkpoint,
    retry_once,
    task_subprocess,
    verify_on_disk,
    write_checkpoint,
)
from qa_skills.agent_log import (  # noqa: E402
    write_agent_output,
    write_merged_agent_output,
)
from qa_skills.budget import (  # noqa: E402
    batch_id as _batch_id,
    is_completed,
    load_batch_state,
    mark_completed,
    save_batch_state,
    summarize_prior_batches,
)
from qa_skills.final_gate import run_final_gate  # noqa: E402
from qa_skills.learnings import persist_learnings  # noqa: E402
from qa_skills.path_planner import compute_expected_files  # noqa: E402
from qa_skills.prompt_builder import (  # noqa: E402
    PromptTooLarge,
    build_test_gen_prompt,
)
from qa_skills.quality import compute_quality_score  # noqa: E402
from qa_skills.report_builder import build_report_data  # noqa: E402
from qa_skills.runner import run_tests  # noqa: E402
from qa_skills.server import build_server_plan, is_reachable  # noqa: E402
from qa_skills.state import read_state, write_state  # noqa: E402
from qa_skills.strategy import decide_category, has_signal  # noqa: E402
from qa_skills.types import ServerPlan  # noqa: E402
from qa_skills.validators import validate_path  # noqa: E402


CATEGORIES = ("unit", "api", "ui", "security", "a11y", "contract")
CATEGORY_TO_AGENT = {
    "unit":     "qa-unit-test",
    "api":      "qa-api-test",
    "ui":       "qa-ui-test",
    "security": "qa-security-test",
    "a11y":     "qa-a11y-test",
    "contract": "qa-contract-test",
}

DOMAIN_ANALYZER_CHUNK = 8
"""Max expected_files per qa-domain-analyzer Task call.

Bounded payload keeps the sub-agent's context small enough that it actually
reads each source file rather than skimming. Larger categories are split
across multiple calls; briefs are merged into a single file per category.
"""

DISPATCH_BATCH_SIZE = 3
"""How many files share one batch (= one runner invocation + one merged log).

Inside a batch, the driver still invokes the sub-agent **once per file** so
each Task call sees exactly one expected_file. The batch boundary is the
unit for: runner execution, agent_output log, batch_state checkpoint.
"""

STATUS_RANK = {"passed": 0, "skipped": 1, "partial": 2, "error": 3}
"""Status severity used to collapse per-file results into a batch status."""


# ---------------------------------------------------------------------------
# Phase 0 — setup
# ---------------------------------------------------------------------------


def phase_0_setup(
    *,
    project_root: str,
    locale: str,
    mode: str,
    categories: Optional[list[str]],
    force_full: bool,
    interactive: bool,
    run_id: Optional[str] = None,
) -> dict:
    """Build RunContext + write checkpoint(0)."""
    rc = build_run_context(
        project_root=project_root,
        locale=locale,
        mode=mode,
        categories=categories,
        force_full=force_full,
        interactive=interactive,
        run_id=run_id,
    )
    phase_checkpoint(rc, phase=0, name="setup")
    return rc


# ---------------------------------------------------------------------------
# Phase 1 — scan
# ---------------------------------------------------------------------------


def phase_1_scan(rc: dict, task_call: TaskCall) -> dict:
    """Invoke qa-code-analyzer + verify analysis.json on disk.

    Writes (via sub-agent): ``${logs_dir}/analysis.json``
    Returns: the parsed Analysis dataclass-as-dict by re-reading the file.

    On failure: raises `SystemExit(2)` with JSON error on stdout.
    """
    analyzer_payload = {
        "run_id": rc["run_id"],
        "project_root": rc["project_root"],
        "analysis_path": rc["analysis_path"],
        "locale": rc["locale"],
    }

    try:
        task_call("qa-code-analyzer", analyzer_payload)
    except TaskError as e:
        _fail(2, "analyzer_task_failed", str(e))

    raw = verify_on_disk(rc["analysis_path"])
    if raw is None:
        _fail(2, "analysis_json_missing", rc["analysis_path"])

    try:
        analysis = load_analysis(rc["analysis_path"])
    except AnalysisValidationError as e:
        _fail(2, "analysis_invalid", str(e))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        _fail(2, "analysis_unreadable", f"{type(e).__name__}: {e}")

    rc["language"] = analysis.language
    rc["analysis_summary"] = {
        "language":      analysis.language,
        "modules":       len(analysis.modules),
        "routes":        len(analysis.routes),
        "api_routes":    sum(1 for _ in analysis.api_routes()),
        "frontend_kind": analysis.frontend_kind,
    }
    phase_checkpoint(rc, phase=1, name="scan")
    return rc["analysis_summary"]


# ---------------------------------------------------------------------------
# Phase 2 — strategy
# ---------------------------------------------------------------------------


def phase_2_strategy(rc: dict, *, allow_start: bool = False) -> dict:
    """Build expected_files + server_plan + planned/skipped category list.

    Writes:
      - ``${logs_dir}/expected_files.json``
      - ``${logs_dir}/strategy.json``

    Returns the strategy dict (also persisted to disk).

    On failure: raises `SystemExit(3)`.
    """
    try:
        analysis = load_analysis(rc["analysis_path"])
    except (AnalysisValidationError, FileNotFoundError, json.JSONDecodeError) as e:
        _fail(3, "analysis_reload_failed", f"{type(e).__name__}: {e}")

    # --- expected_files: deterministic path layout per category --------------
    expected_files: dict[str, list[dict]] = {}
    try:
        for cat in CATEGORIES:
            entries = compute_expected_files(cat, analysis, analysis.language)
            expected_files[cat] = [ef.to_dict() for ef in entries]
    except Exception as e:  # pragma: no cover — path planner errors surface here
        _fail(3, "path_planner_failed", f"{type(e).__name__}: {e}")

    atomic_write_json(Path(rc["expected_files_path"]), expected_files)

    # --- server_plan: built once, threaded to ui/a11y dispatch ---------------
    plan = build_server_plan(analysis, mode=rc["mode"], allow_start_explicit=allow_start)
    server_reachable = bool(plan.url) and is_reachable(plan.url)
    server_plan_dict = _server_plan_to_dict(plan)

    # --- planned/skipped categories using strategy gates ---------------------
    requested = rc["categories"] or list(CATEGORIES)
    planned: list[str] = []
    skipped: list[dict] = []

    for cat in CATEGORIES:
        if cat not in requested:
            skipped.append({"name": cat, "reason": "disabled_by_caller"})
            continue
        if cat in ("ui", "a11y"):
            ok, reason = decide_category(cat, analysis, plan, server_reachable)
        else:
            ok, reason = has_signal(cat, analysis)
        if ok:
            planned.append(cat)
        else:
            skipped.append({"name": cat, "reason": reason})

    # --- build strategy.json -------------------------------------------------
    strategy = {
        "summary": {
            "modules_total":      len(analysis.modules),
            "categories_planned": planned,
            "categories_skipped": skipped,
        },
        "agents": [
            {"agent": CATEGORY_TO_AGENT[c], "category": c,
             "expected_files_count": len(expected_files[c])}
            for c in planned
        ],
        "server_plan": server_plan_dict,
        "server_reachable": server_reachable,
        "budgets": {
            "global_token_cap":         200_000,
            "per_agent_max_tokens":     80_000,
            "per_agent_timeout_seconds": 600,
        },
        "mode":         rc["mode"],
        "run_id":       rc["run_id"],
        "generated_at": now_iso(),
    }
    atomic_write_json(Path(rc["strategy_path"]), strategy)

    rc["strategy"] = strategy
    rc["server_plan"] = server_plan_dict
    phase_checkpoint(rc, phase=2, name="strategy")
    return strategy


def _server_plan_to_dict(plan: ServerPlan) -> dict:
    return {
        "url":             plan.url,
        "start_command":   plan.start_command,
        "start_allowed":   plan.start_allowed,
        "timeout_seconds": plan.timeout_seconds,
        "cleanup_pid":     plan.cleanup_pid,
    }


# ---------------------------------------------------------------------------
# Phase 2.7 — Domain learn (forced per planned category)
# ---------------------------------------------------------------------------


def phase_2_7_domain_learn(rc: dict, task_call: TaskCall) -> dict:
    """Invoke qa-domain-analyzer once per planned category.

    For each category:
      - chunk expected_files into ≤ DOMAIN_ANALYZER_CHUNK groups
      - invoke qa-domain-analyzer per chunk with `retry_once` against the
        chunk's tmp output file
      - merge per-chunk briefs into a single
        ``${logs_dir}/domain_brief_<cat>.json``
      - on persistent failure, write an empty placeholder so Phase 3 has a
        deterministic file shape AND append `domain_brief_unavailable:<cat>`
        to ``${logs_dir}/warnings.json``

    Returns a small summary dict: ``{cat: {chunks, behaviors_total, ok}}``.

    Never raises — domain learn failures degrade gracefully to "no brief"
    rather than aborting the run.
    """
    expected_files = verify_on_disk(rc["expected_files_path"]) or {}
    planned = (rc.get("strategy") or {}).get("summary", {}).get(
        "categories_planned", []
    )

    summary: dict[str, dict] = {}
    warnings: list[str] = []

    for cat in planned:
        cat_files = expected_files.get(cat, [])
        if not cat_files:
            _write_brief_placeholder(rc, cat, reason="no_expected_files")
            summary[cat] = {"chunks": 0, "behaviors_total": 0, "ok": False}
            continue

        chunks = list(_chunked(cat_files, DOMAIN_ANALYZER_CHUNK))
        merged_briefs: list[dict] = []
        any_chunk_failed = False

        for idx, chunk in enumerate(chunks):
            chunk_path = Path(rc["logs_dir"]) / f"_brief_{cat}_chunk_{idx:03d}.json"
            payload = _domain_analyzer_payload(rc, cat, chunk, chunk_path)
            r = retry_once(
                task_call,
                agent="qa-domain-analyzer",
                payload=payload,
                artifact_path=chunk_path,
                on_failure_prompt_suffix=(
                    "Your previous output did not appear at chunk_path on disk. "
                    "Write your brief JSON atomically to the chunk_path provided "
                    "in this payload. Emit at least one behavior per expected_file "
                    "or an empty `behaviors: []` entry."
                ),
            )
            if r.ok and isinstance(r.artifact, dict):
                merged_briefs.extend(r.artifact.get("briefs", []) or [])
            else:
                any_chunk_failed = True

        if merged_briefs:
            atomic_write_json(
                Path(rc["logs_dir"]) / f"domain_brief_{cat}.json",
                {
                    "agent":    "qa-domain-analyzer",
                    "category": cat,
                    "status":   "partial" if any_chunk_failed else "passed",
                    "briefs":   merged_briefs,
                },
            )
            summary[cat] = {
                "chunks": len(chunks),
                "behaviors_total": sum(
                    len(b.get("behaviors") or []) for b in merged_briefs
                ),
                "ok": True,
            }
        else:
            _write_brief_placeholder(rc, cat, reason="empty_after_retry")
            warnings.append(f"domain_brief_unavailable:{cat}")
            summary[cat] = {"chunks": len(chunks), "behaviors_total": 0, "ok": False}

        for idx in range(len(chunks)):
            tmp = Path(rc["logs_dir"]) / f"_brief_{cat}_chunk_{idx:03d}.json"
            if tmp.exists():
                tmp.unlink()

    _append_warnings(rc, warnings)
    phase_checkpoint(rc, phase=2.7, name="domain_learn")
    return summary


def _domain_analyzer_payload(
    rc: dict, category: str, chunk: list[dict], chunk_path: Path
) -> dict:
    """Build the bounded sub-agent payload for one chunk."""
    return {
        "run_id":         rc["run_id"],
        "project_root":   rc["project_root"],
        "category":       category,
        "language":       rc.get("language"),
        "logs_dir":       rc["logs_dir"],
        "chunk_path":     str(chunk_path),
        "expected_files": chunk,
        "analysis_path":  rc["analysis_path"],
    }


def _write_brief_placeholder(rc: dict, category: str, *, reason: str) -> None:
    """Write an empty brief file so Phase 3 has a deterministic input."""
    atomic_write_json(
        Path(rc["logs_dir"]) / f"domain_brief_{category}.json",
        {
            "agent":    "qa-domain-analyzer",
            "category": category,
            "status":   "unavailable",
            "reason":   reason,
            "briefs":   [],
        },
    )


def _append_warnings(rc: dict, new_warnings: list[str]) -> None:
    """Atomically append to ``${logs_dir}/warnings.json`` (list of strings)."""
    if not new_warnings:
        return
    path = Path(rc["logs_dir"]) / "warnings.json"
    existing = verify_on_disk(path)
    current: list[str] = list(existing) if isinstance(existing, list) else []
    merged = sorted(set(current) | set(new_warnings))
    atomic_write_json(path, merged)


def _chunked(items: list, size: int):
    """Yield successive size-sized lists from items."""
    if size <= 0:
        raise ValueError("size must be positive")
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------------------
# Phase 3 — Dispatch (file-per-Task, driver-owned execution + telemetry)
# ---------------------------------------------------------------------------


def phase_3_dispatch(rc: dict, task_call: TaskCall) -> dict:
    """Drive test generation: one Task call per expected_file.

    The driver is the entire enforcement layer:
      - reads expected_files + domain_brief per category
      - splits into batches of DISPATCH_BATCH_SIZE
      - for each file: builds a tiny prompt, invokes the sub-agent, verifies
        the file landed on disk at the contracted path, validates the path
        regex, retries once on disk miss
      - after each batch: runs the test runner, writes
        ``agent_output_<agent>_batch_NNN.json``, updates ``batch_state.json``
      - after each category: writes merged ``agent_output_<agent>.json`` and
        ``execution_<agent>.json`` (sum across batches)

    Returns a small per-agent summary dict.

    Never raises. Per-file failures degrade to status `error` in the agent
    output; persistent failures appear in the merged status (`partial` or
    `error`) and in ``warnings.json``.
    """
    expected = verify_on_disk(rc["expected_files_path"]) or {}
    planned = (rc.get("strategy") or {}).get("summary", {}).get(
        "categories_planned", []
    )
    server_plan = (rc.get("strategy") or {}).get("server_plan")
    state = load_batch_state(Path(rc["logs_dir"]))
    warnings: list[str] = []
    summary: dict[str, dict] = {}

    for cat in planned:
        agent = CATEGORY_TO_AGENT[cat]
        cat_files = expected.get(cat, [])
        if not cat_files:
            summary[cat] = _agent_summary(agent, 0, 0, 0, 0)
            continue

        brief_by_path = _index_brief_by_path(rc, cat)
        batches = _split_files_into_batches(cat_files, DISPATCH_BATCH_SIZE)
        batch_results: list[dict] = []
        prior_paths: list[str] = []

        for batch_idx, batch_files in enumerate(batches):
            bid = _batch_id(cat, batch_idx)
            if is_completed(state, bid):
                continue

            per_file_outputs = _dispatch_batch_files(
                rc=rc,
                task_call=task_call,
                agent=agent,
                category=cat,
                batch_files=batch_files,
                brief_by_path=brief_by_path,
                server_plan=server_plan,
                prior_summary=prior_paths,
                warnings=warnings,
            )

            executed = _run_batch_tests(
                rc, category=cat, file_outputs=per_file_outputs
            )

            batch_status = _collapse_status(
                o.get("status", "error") for o in per_file_outputs
            )
            batch_payload = {
                "agent":             agent,
                "status":            batch_status,
                "outputs":           per_file_outputs,
                "execution_result":  executed,
            }
            write_agent_output(
                Path(rc["logs_dir"]), agent, batch_payload, batch_idx=batch_idx
            )

            ok_paths = [
                o["path"] for o in per_file_outputs
                if o.get("status") == "passed" and o.get("path")
            ]
            mark_completed(state, bid, ok_paths)
            save_batch_state(Path(rc["logs_dir"]), state)
            prior_paths = _refresh_prior(state, cat)
            batch_results.append(batch_payload)

        merged = write_merged_agent_output(
            Path(rc["logs_dir"]), agent, batch_results
        )
        merged_payload = verify_on_disk(merged) or {}
        atomic_write_json(
            Path(rc["logs_dir"]) / f"execution_{agent}.json",
            _merge_execution_results(batch_results, category=cat),
        )

        summary[cat] = _agent_summary(
            agent,
            files_attempted=len(cat_files),
            files_emitted=sum(
                1 for o in merged_payload.get("outputs", [])
                if o.get("status") == "passed"
            ),
            batches=len(batches),
            warnings=len([w for w in warnings if w.startswith(f"{agent}:")]),
        )

    _append_warnings(rc, warnings)
    phase_checkpoint(rc, phase=3, name="dispatch")
    return summary


# ----- Phase 3 helpers ----------------------------------------------------


def _index_brief_by_path(rc: dict, category: str) -> dict[str, dict]:
    """Build a {expected_file_path: brief_entry} map for one category."""
    brief = verify_on_disk(
        Path(rc["logs_dir"]) / f"domain_brief_{category}.json"
    ) or {}
    out: dict[str, dict] = {}
    for b in brief.get("briefs", []) or []:
        if isinstance(b, dict) and b.get("expected_file"):
            out[b["expected_file"]] = b
    return out


def _split_files_into_batches(files: list[dict], size: int) -> list[list[dict]]:
    return [files[i : i + size] for i in range(0, len(files), size)]


def _dispatch_batch_files(
    *,
    rc: dict,
    task_call: TaskCall,
    agent: str,
    category: str,
    batch_files: list[dict],
    brief_by_path: dict[str, dict],
    server_plan: Optional[dict],
    prior_summary: list[str],
    warnings: list[str],
) -> list[dict]:
    """Invoke the sub-agent once per file. Returns one output entry per file."""
    outputs: list[dict] = []
    pr = Path(rc["project_root"])
    language = rc.get("language") or "typescript"

    for ef in batch_files:
        path_rel = ef.get("path") or ""
        covers = ef.get("covers") or []
        brief_slice = brief_by_path.get(path_rel)
        try:
            payload = build_test_gen_prompt(
                agent=agent,
                category=category,
                expected_file=ef,
                domain_brief=brief_slice,
                language=language,
                project_root=str(pr),
                run_id=rc["run_id"],
                prior_summary=prior_summary,
                server_plan=server_plan if category in ("ui", "a11y") else None,
                frontend_kind=(
                    (rc.get("analysis_summary") or {}).get("frontend_kind")
                    if category in ("ui", "a11y") else None
                ),
            )
        except PromptTooLarge as e:
            warnings.append(f"{agent}:prompt_too_large:{path_rel}:{e.size}")
            outputs.append(
                _empty_output(agent, ef, "error", reason=f"prompt_too_large:{e.size}")
            )
            continue
        except (TypeError, ValueError) as e:
            warnings.append(f"{agent}:prompt_build_failed:{path_rel}:{e}")
            outputs.append(_empty_output(agent, ef, "error", reason=str(e)))
            continue

        full_path = pr / path_rel
        result = _invoke_with_disk_verification(
            task_call, agent, payload, full_path,
            on_failure_prompt_suffix=(
                f"Your previous output did not write {path_rel} to disk. "
                f"Write the test file at exactly this path inside project_root "
                f"and emit valid {language} test code."
            ),
        )

        if not full_path.is_file():
            warnings.append(f"{agent}:file_not_written:{path_rel}")
            outputs.append(_empty_output(agent, ef, "error", reason="file_not_written"))
            continue

        ok, reason = validate_path(path_rel, language=language)
        if not ok:
            try:
                full_path.unlink()
            except OSError:
                pass
            warnings.append(f"{agent}:{reason}")
            outputs.append(_empty_output(agent, ef, "error", reason=reason))
            continue

        outputs.append(_normalize_output(agent, ef, result, default_status="passed"))

    return outputs


def _invoke_with_disk_verification(
    task_call: TaskCall,
    agent: str,
    payload: dict,
    artifact_path: Path,
    *,
    on_failure_prompt_suffix: str,
) -> dict:
    """Call Task; retry once if the artifact didn't appear on disk."""
    try:
        result = task_call(agent, payload)
    except TaskError as e:
        result = {"status": "error", "reason": f"task_error:{e}"}

    if artifact_path.is_file():
        return result

    retry_payload = dict(payload)
    retry_payload["retry_hint"] = on_failure_prompt_suffix
    try:
        result = task_call(agent, retry_payload)
    except TaskError as e:
        result = {"status": "error", "reason": f"task_error:{e}"}
    return result


def _normalize_output(
    agent: str, expected_file: dict, result: dict, *, default_status: str
) -> dict:
    """Coerce the sub-agent return into a stable per-file output entry."""
    sub_outputs = (result or {}).get("outputs") or []
    first = sub_outputs[0] if isinstance(sub_outputs, list) and sub_outputs else {}
    status = result.get("status") or first.get("status") or default_status
    if not isinstance(status, str):
        status = default_status

    return {
        "agent":           agent,
        "source_module":   _first_str(first.get("source_module"))
                           or _first_cover_module(expected_file),
        "path":            expected_file.get("path"),
        "covers":          list(expected_file.get("covers") or []),
        "tests_written":   _int_or(first.get("tests_written"), 0),
        "tests_passing":   _int_or(first.get("tests_passing"), 0),
        "assertions_covered": list(first.get("assertions_covered") or []),
        "hints_used":      list(first.get("hints_used") or []),
        "skipped_hints":   list(first.get("skipped_hints") or []),
        "status":          status,
    }


def _empty_output(agent: str, expected_file: dict, status: str, *, reason: str) -> dict:
    return {
        "agent":           agent,
        "source_module":   _first_cover_module(expected_file),
        "path":            expected_file.get("path"),
        "covers":          list(expected_file.get("covers") or []),
        "tests_written":   0,
        "tests_passing":   0,
        "assertions_covered": [],
        "hints_used":      [],
        "skipped_hints":   [],
        "status":          status,
        "reason":          reason,
    }


def _first_cover_module(ef: dict) -> str:
    covers = ef.get("covers") or []
    return covers[0] if covers else ""


def _first_str(v: Any) -> str:
    return v if isinstance(v, str) else ""


def _int_or(v: Any, default: int) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def _collapse_status(statuses) -> str:
    """Reduce a list of per-file statuses to a single batch status."""
    worst = 0
    for s in statuses:
        head = s.split(":", 1)[0] if isinstance(s, str) else "error"
        worst = max(worst, STATUS_RANK.get(head, 3))
    return ["passed", "skipped", "partial", "error"][worst]


def _refresh_prior(state: dict, category: str) -> list[str]:
    """Flatten `summarize_prior_batches` output → a path-only list capped later."""
    paths: list[str] = []
    for entry in summarize_prior_batches(state, category):
        for p in entry.get("paths", []) or []:
            if isinstance(p, str):
                paths.append(p)
    return paths


def _run_batch_tests(rc: dict, *, category: str, file_outputs: list[dict]) -> dict:
    """Run the project's test runner against the files emitted in this batch."""
    pr = Path(rc["project_root"])
    language = rc.get("language") or "typescript"
    files_to_run = [
        str(pr / o["path"])
        for o in file_outputs
        if o.get("path") and o.get("status") != "error"
    ]
    if not files_to_run:
        return {
            "category":     category,
            "runner":       "skipped",
            "total":        0,
            "passed":       0,
            "failed":       0,
            "skipped":      0,
            "duration_ms":  0,
            "failures":     [],
            "exit_code":    0,
            "note":         "no_files_to_run",
        }
    return run_tests(
        category=category,
        project_root=pr,
        files=files_to_run,
        language=language,
        timeout_seconds=600,
    )


def _merge_execution_results(batch_results: list[dict], *, category: str) -> dict:
    """Sum per-batch execution_result dicts into one canonical result.

    `runner` is taken from the first non-empty batch. `failures[]` are
    concatenated in batch order. `exit_code` collapses to the most severe.
    """
    runner = ""
    total = passed = failed = skipped = duration_ms = exit_code = 0
    failures: list[dict] = []

    for br in batch_results:
        er = br.get("execution_result") or {}
        if not runner:
            runner = er.get("runner") or runner
        total       += _int_or(er.get("total"), 0)
        passed      += _int_or(er.get("passed"), 0)
        failed      += _int_or(er.get("failed"), 0)
        skipped     += _int_or(er.get("skipped"), 0)
        duration_ms += _int_or(er.get("duration_ms"), 0)
        ec = _int_or(er.get("exit_code"), 0)
        if ec > exit_code:
            exit_code = ec
        for f in (er.get("failures") or [])[:200]:
            failures.append(f)

    return {
        "category":     category,
        "runner":       runner or "skipped",
        "total":        total,
        "passed":       passed,
        "failed":       failed,
        "skipped":      skipped,
        "duration_ms":  duration_ms,
        "failures":     failures,
        "exit_code":    exit_code,
    }


def _agent_summary(
    agent: str,
    files_attempted: int = 0,
    files_emitted: int = 0,
    batches: int = 0,
    warnings: int = 0,
) -> dict:
    return {
        "agent":           agent,
        "files_attempted": files_attempted,
        "files_emitted":   files_emitted,
        "batches":         batches,
        "warnings":        warnings,
    }


# ---------------------------------------------------------------------------
# Phase 5 — Flaky detection (LLM sub-agent, bounded)
# ---------------------------------------------------------------------------


def phase_5_flaky(rc: dict, task_call: TaskCall) -> dict:
    """Invoke qa-flaky-detector once for the full run.

    Skipped if every agent status is `error` / `skipped` (nothing useful to
    re-run). Writes `flaky.json` on disk; degrades to empty list on failure.
    """
    logs_dir = Path(rc["logs_dir"])
    any_passable = False
    test_paths: list[str] = []
    for agent_log in sorted(logs_dir.glob("agent_output_qa-*-test.json")):
        data = verify_on_disk(agent_log) or {}
        status = (data.get("status") or "error").split(":", 1)[0]
        if status in ("passed", "partial"):
            any_passable = True
        for o in data.get("outputs", []) or []:
            if isinstance(o, dict) and o.get("path") and o.get("status") == "passed":
                test_paths.append(o["path"])

    flaky_path = logs_dir / "flaky.json"
    if not any_passable or not test_paths:
        atomic_write_json(flaky_path, {"flaky_tests": [], "runs_completed": 0,
                                       "skipped": "no_passable_tests"})
        phase_checkpoint(rc, phase=5, name="flaky")
        return {"flaky_count": 0, "skipped": True}

    payload = {
        "run_id":       rc["run_id"],
        "project_root": rc["project_root"],
        "logs_dir":     str(logs_dir),
        "test_paths":   sorted(set(test_paths))[:50],
        "flaky_path":   str(flaky_path),
    }
    try:
        task_call("qa-flaky-detector", payload)
    except TaskError:
        pass

    if not flaky_path.is_file():
        atomic_write_json(flaky_path, {"flaky_tests": [], "runs_completed": 0,
                                       "skipped": "agent_no_write"})

    data = verify_on_disk(flaky_path) or {}
    phase_checkpoint(rc, phase=5, name="flaky")
    return {"flaky_count": len(data.get("flaky_tests") or [])}


# ---------------------------------------------------------------------------
# Phase 5.5 — Persist learnings (pure Python)
# ---------------------------------------------------------------------------


def phase_5_5_learnings(rc: dict) -> dict:
    """Write learnings.json + learnings.log. Single owner of those files."""
    logs_dir = Path(rc["logs_dir"])
    all_outputs: list[dict] = []
    for f in sorted(logs_dir.glob("agent_output_qa-*-test.json")):
        data = verify_on_disk(f)
        if isinstance(data, dict):
            all_outputs.append(data)

    flaky_data = verify_on_disk(logs_dir / "flaky.json") or {}
    flaky_tests = flaky_data.get("flaky_tests") or []

    summary = persist_learnings(
        rc["project_root"],
        all_test_outputs=all_outputs,
        flaky_tests=flaky_tests,
        run_id=rc["run_id"],
    )
    atomic_write_json(logs_dir / "learnings_summary.json", summary)
    phase_checkpoint(rc, phase=5.5, name="learnings")
    return summary


# ---------------------------------------------------------------------------
# Phase 6 — State write (pure Python)
# ---------------------------------------------------------------------------


def phase_6_state_write(rc: dict) -> dict:
    """Write test-state.json. Carries over unchanged modules from prior run."""
    logs_dir = Path(rc["logs_dir"])
    analysis_path = rc["analysis_path"]
    analysis = _load_analysis_or_fail(analysis_path)

    test_paths_by_module: dict[str, list[str]] = {}
    execution_result_by_module: dict[str, str] = {}

    for f in sorted(logs_dir.glob("agent_output_qa-*-test.json")):
        data = verify_on_disk(f) or {}
        for o in data.get("outputs", []) or []:
            if not isinstance(o, dict):
                continue
            src = o.get("source_module") or (o.get("covers") or [""])[0]
            path = o.get("path")
            if not (src and path):
                continue
            test_paths_by_module.setdefault(src, []).append(path)
            execution_result_by_module[src] = (
                "passed" if o.get("status") == "passed"
                else ("failed" if o.get("status") == "error" else "partial")
            )

    prior_state_path = Path(rc["state_path"])
    prior = read_state(prior_state_path) if prior_state_path.is_file() else None

    state = write_state(
        rc["state_path"],
        run_id=rc["run_id"],
        generated_at=now_iso(),
        analysis=analysis,
        test_paths_by_module=test_paths_by_module,
        execution_result_by_module=execution_result_by_module,
        prior_state=prior,
    )
    phase_checkpoint(rc, phase=6, name="state_write")
    return {"modules": len(state.get("modules", []))}


# ---------------------------------------------------------------------------
# Phase 8 — Build report (pure Python; replaces qa-coverage-reporter)
# ---------------------------------------------------------------------------


def phase_8_build_report(rc: dict) -> dict:
    """Assemble report-data.json (v2 schema-gated). Driver-side only.

    Never calls qa-coverage-reporter agent. Reads every artifact written
    earlier in the run and pipes through `build_report_data`.
    """
    logs_dir = Path(rc["logs_dir"])
    project_root = Path(rc["project_root"])
    analysis = _load_analysis_or_fail(rc["analysis_path"])

    all_test_outputs = _collect_agent_outputs(logs_dir)
    execution_results = _collect_execution_results(logs_dir)

    flaky_data = verify_on_disk(logs_dir / "flaky.json") or {}
    flaky_tests = flaky_data.get("flaky_tests") or []

    state_data = verify_on_disk(rc["state_path"])
    strategy   = rc.get("strategy") or {}

    warnings_list = verify_on_disk(logs_dir / "warnings.json")
    warnings = warnings_list if isinstance(warnings_list, list) else []

    learnings_summary = verify_on_disk(logs_dir / "learnings_summary.json")

    report = build_report_data(
        run_id=rc["run_id"],
        project_root=str(project_root),
        analysis=analysis,
        all_test_outputs=all_test_outputs,
        env_categories_removed=strategy.get("env_categories_removed") or [],
        env_installs_performed=strategy.get("env_installs_performed") or [],
        state=state_data,
        flaky_tests=flaky_tests,
        run_type="full",
        timeline=strategy.get("timeline") or [],
        locale=rc.get("locale", "en"),
        warnings=warnings,
        execution_results=execution_results,
        learnings_summary=learnings_summary if isinstance(learnings_summary, dict) else None,
    )

    if report.get("version") != "2.0":
        return {"status": "error", "reason": f"report_version:{report.get('version')!r}"}

    required_keys = {"pct", "covered_items", "missing_items", "total",
                     "files", "stub_files", "status", "execution"}
    for cat, info in (report.get("coverage_by_category") or {}).items():
        if not isinstance(info, dict):
            continue
        missing = required_keys - set(info.keys())
        if missing:
            return {"status": "error",
                    "reason": f"coverage_missing_keys:{cat}:{sorted(missing)}"}

    out = project_root / "test-reports" / "report-data.json"
    atomic_write_json(out, report)
    phase_checkpoint(rc, phase=8, name="report")
    return {"status": "ok", "path": str(out),
            "quality_score": report.get("quality_score"),
            "version": report.get("version")}


# ---------------------------------------------------------------------------
# Phase 7 — Quality (pure Python, mutates report-data.json in place)
# ---------------------------------------------------------------------------


def phase_7_quality(rc: dict) -> dict:
    """Compute quality_score from report-data.json and patch it back in.

    `build_report_data` may already include a score; this phase re-applies
    `compute_quality_score` against the on-disk artifact so the formula is
    the single source of truth.
    """
    out = Path(rc["project_root"]) / "test-reports" / "report-data.json"
    data = verify_on_disk(out)
    if not isinstance(data, dict):
        return {"status": "error", "reason": "report_data_missing"}
    score = compute_quality_score(
        data.get("coverage_by_category", {}),
        data.get("flaky_tests", []),
        data.get("gaps", []),
    )
    data["quality_score"] = score
    atomic_write_json(out, data)
    phase_checkpoint(rc, phase=7, name="quality")
    return {"quality_score": score}


# ---------------------------------------------------------------------------
# Phase 8b — HTML reporter (LLM sub-agent, bounded)
# ---------------------------------------------------------------------------


def phase_8b_html(rc: dict, task_call: TaskCall) -> dict:
    """Invoke qa-html-reporter against the freshly-built report-data.json."""
    project_root = Path(rc["project_root"])
    report_data_path = project_root / "test-reports" / "report-data.json"
    payload = {
        "run_id":           rc["run_id"],
        "project_root":     str(project_root),
        "report_data_path": str(report_data_path),
        "locale":           rc.get("locale", "en"),
    }
    try:
        task_call("qa-html-reporter", payload)
    except TaskError:
        pass

    reports_dir = project_root / "test-reports"
    html_files = sorted(p for p in reports_dir.glob("report-*.html"))
    html_path = str(html_files[-1]) if html_files else None
    phase_checkpoint(rc, phase=8.5, name="html_report")
    return {"html_path": html_path}


# ---------------------------------------------------------------------------
# Phase 9 — Final gate (pure Python)
# ---------------------------------------------------------------------------


def phase_9_final_gate(rc: dict) -> dict:
    """Run the disk-artifact gate. Records warnings; never aborts."""
    report_data_path = Path(rc["project_root"]) / "test-reports" / "report-data.json"
    result = run_final_gate(
        report_data_path=report_data_path,
        project_root=rc["project_root"],
        run_id=rc["run_id"],
    )
    write_checkpoint(
        rc,
        phase=9,
        phase_name="final_gate",
        completed=True,
        extra={
            "final_status":   result.get("status"),
            "final_warnings": result.get("warnings", []),
        },
    )
    return result


# ----- Phase 5-9 helpers --------------------------------------------------


def _load_analysis_or_fail(analysis_path: str):
    from qa_skills.analysis import (
        AnalysisValidationError,
        load_analysis,
    )
    try:
        return load_analysis(analysis_path)
    except (AnalysisValidationError, FileNotFoundError, json.JSONDecodeError) as e:
        _fail(2, "analysis_reload_failed", f"{type(e).__name__}: {e}")
        raise  # unreachable


def _collect_agent_outputs(logs_dir: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted(logs_dir.glob("agent_output_qa-*-test.json")):
        data = verify_on_disk(f)
        if isinstance(data, dict):
            out.append(data)
    return out


def _collect_execution_results(logs_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(logs_dir.glob("execution_qa-*-test.json")):
        agent = f.stem.removeprefix("execution_")
        data = verify_on_disk(f)
        if isinstance(data, dict):
            out[agent] = data
    return out


# ---------------------------------------------------------------------------
# Failure helper — emits a stable JSON shape to stdout then exits
# ---------------------------------------------------------------------------


def _fail(exit_code: int, reason: str, detail: str) -> None:
    """Print a single-line JSON error to stdout and exit `exit_code`."""
    payload = {
        "status":      "error",
        "phase_reached": _phase_for_exit(exit_code),
        "reason":      reason,
        "detail":      detail,
    }
    print(json.dumps(payload))
    sys.exit(exit_code)


def _phase_for_exit(exit_code: int) -> int:
    return {1: 0, 2: 1, 3: 2}.get(exit_code, -1)


# ---------------------------------------------------------------------------
# Argparse + entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="qa_run")
    p.add_argument("--project-root", required=True)
    p.add_argument("--locale", default="en", choices=("en", "he"))
    p.add_argument("--mode", default="auto", choices=("auto", "interactive"))
    p.add_argument("--categories", default=None,
                   help="Comma-separated subset of: unit,api,ui,security,a11y,contract")
    p.add_argument("--force-full", action="store_true")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--allow-start-server", action="store_true",
                   help="Permit driver to spawn analysis.server_hint.start_command.")
    p.add_argument("--run-id", default=None,
                   help="Reuse a specific run_id (debug/test). Default = new uuid4.")
    return p.parse_args(argv)


def run(
    argv: list[str],
    *,
    task_call: Optional[TaskCall] = None,
) -> dict:
    """Programmatic entrypoint. Returns the final result dict (also printed).

    Tests inject `task_call=stub` to avoid spawning real sub-agents.
    """
    args = parse_args(argv)
    cats = args.categories.split(",") if args.categories else None
    tc = task_call or task_subprocess

    if not Path(args.project_root).exists():
        _fail(1, "project_root_missing", args.project_root)

    rc = phase_0_setup(
        project_root=args.project_root,
        locale=args.locale,
        mode=args.mode,
        categories=cats,
        force_full=args.force_full,
        interactive=args.interactive,
        run_id=args.run_id,
    )

    phase_1_scan(rc, tc)
    strategy = phase_2_strategy(rc, allow_start=args.allow_start_server)
    domain_summary = phase_2_7_domain_learn(rc, tc)
    dispatch_summary = phase_3_dispatch(rc, tc)
    flaky_summary = phase_5_flaky(rc, tc)
    learnings_summary = phase_5_5_learnings(rc)
    state_summary = phase_6_state_write(rc)
    report_summary = phase_8_build_report(rc)
    quality_summary = phase_7_quality(rc)
    html_summary = phase_8b_html(rc, tc)
    final_gate = phase_9_final_gate(rc)

    result = {
        "status":        "ok",
        "phase_reached": 9,
        "run_id":        rc["run_id"],
        "language":      rc.get("language"),
        "analysis":      rc.get("analysis_summary"),
        "strategy":      {
            "categories_planned": strategy["summary"]["categories_planned"],
            "categories_skipped": strategy["summary"]["categories_skipped"],
        },
        "domain_briefs":     domain_summary,
        "dispatch":          dispatch_summary,
        "flaky":             flaky_summary,
        "learnings":         learnings_summary,
        "state":             state_summary,
        "report":            report_summary,
        "quality":           quality_summary,
        "html":              html_summary,
        "final_gate":        final_gate,
        "quality_score":     quality_summary.get("quality_score"),
        "final_status":      final_gate.get("status"),
        "paths": {
            "analysis":       rc["analysis_path"],
            "expected_files": rc["expected_files_path"],
            "strategy":       rc["strategy_path"],
            "logs_dir":       rc["logs_dir"],
            "state":          rc["state_path"],
            "report_data":    str(Path(rc["project_root"]) / "test-reports" / "report-data.json"),
            "report_html":    html_summary.get("html_path"),
        },
    }
    return result


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Returns process exit code."""
    argv = argv if argv is not None else sys.argv[1:]
    result = run(argv)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
