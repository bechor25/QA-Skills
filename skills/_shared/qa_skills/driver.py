"""QA-Skills v2 driver primitives.

The driver coordinates the pipeline phases. LLM sub-agents are invoked via
the `TaskCall` seam — runtime injects a subprocess implementation, tests
inject a stub.

Public surface:

- `TaskCall`              — callable signature for sub-agent invocation.
- `task_subprocess`       — default runtime implementation. Spawns the
                            sub-agent via the `claude` CLI in headless mode.
- `verify_on_disk`        — read+parse JSON if present, else None.
- `retry_once`            — invoke a Task call, verify a disk artifact, retry
                            once with a prompt suffix when verification fails.
- `build_run_context`     — deterministic Phase-0 run-context shape.
- `write_checkpoint`      — atomic checkpoint write.
- `phase_checkpoint`      — convenience wrapper for the per-phase pattern.

This module never mutates global state. All state lives in the returned
`RunContext` dict or under `RunContext["logs_dir"]` / `checkpoint_dir`.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = [
    "TaskCall",
    "TaskError",
    "TaskTimeout",
    "task_subprocess",
    "verify_on_disk",
    "retry_once",
    "build_run_context",
    "write_checkpoint",
    "phase_checkpoint",
    "atomic_write_json",
    "now_iso",
]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


TaskCall = Callable[[str, dict], dict]
"""Sub-agent invocation seam.

Signature: ``task_call(agent_name, payload_dict) -> result_dict``.

Runtime injects `task_subprocess`; tests inject a stub.
"""


class TaskError(RuntimeError):
    """Sub-agent process failed (non-zero exit, unparseable stdout, etc.)."""


class TaskTimeout(TaskError):
    """Sub-agent process exceeded `timeout` seconds."""


# ---------------------------------------------------------------------------
# Time + atomic I/O helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    """ISO-8601 UTC timestamp with seconds resolution + trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically via temp file + os.replace.

    The directory must exist. Parent-dir creation is the caller's job — keeps
    failure modes explicit at phase boundaries.
    """
    path = Path(path)
    payload_str = json.dumps(payload, indent=2, sort_keys=False)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=str(path.parent), prefix=".tmp-", suffix=".json"
    ) as tmp:
        tmp.write(payload_str)
        tmp.write("\n")
        tmp_path = tmp.name
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Task subprocess seam
# ---------------------------------------------------------------------------


def task_subprocess(
    agent: str,
    payload: dict,
    *,
    timeout: int = 600,
    claude_bin: str = "claude",
    extra_env: Optional[dict] = None,
) -> dict:
    """Default runtime implementation of `TaskCall`.

    Spawns the `claude` CLI in headless mode against the requested sub-agent,
    feeds it the payload as JSON on stdin, expects a single JSON object on
    stdout.

    Tests should inject a stub instead — this function performs real IO.

    Raises:
        TaskTimeout: process exceeded `timeout` seconds.
        TaskError:   non-zero exit, or stdout not valid JSON.
    """
    payload_str = json.dumps(payload)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    try:
        proc = subprocess.run(
            [claude_bin, "-p", agent, "--input-format", "json"],
            input=payload_str,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise TaskTimeout(f"task {agent} exceeded {timeout}s") from e
    except FileNotFoundError as e:
        raise TaskError(f"claude binary not found: {claude_bin}") from e

    if proc.returncode != 0:
        raise TaskError(
            f"task {agent} exited {proc.returncode}: {proc.stderr[:500]}"
        )

    raw = proc.stdout.strip()
    if not raw:
        raise TaskError(f"task {agent} produced empty stdout")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise TaskError(
            f"task {agent} stdout not JSON: {e}; first 200 chars: {raw[:200]!r}"
        ) from e


# ---------------------------------------------------------------------------
# Disk verification
# ---------------------------------------------------------------------------


def verify_on_disk(path: Path | str) -> Optional[dict]:
    """Return parsed JSON if file exists and parses; None otherwise.

    Never raises on `FileNotFoundError` / `JSONDecodeError` — both signal
    "not on disk" to the caller. Other I/O errors propagate (genuine bugs).
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Retry-once around Task + disk verification
# ---------------------------------------------------------------------------


@dataclass
class RetryResult:
    """Outcome of `retry_once`."""

    ok: bool
    """True iff disk artifact present after first or second attempt."""

    attempts: int
    """1 or 2."""

    last_result: dict
    """The dict returned by the last Task call (may be empty on hard error)."""

    artifact: Optional[dict]
    """Parsed disk artifact, or None when both attempts failed."""


def retry_once(
    task_call: TaskCall,
    *,
    agent: str,
    payload: dict,
    artifact_path: Path,
    on_failure_prompt_suffix: str,
    payload_retry_key: str = "retry_hint",
) -> RetryResult:
    """Invoke a Task; verify a disk artifact; retry once on failure.

    Pattern:
      1. Call `task_call(agent, payload)`.
      2. Check `artifact_path` on disk via `verify_on_disk`.
      3. If missing → patch `payload[payload_retry_key] = on_failure_prompt_suffix`
         and retry once.
      4. Return a `RetryResult`.

    The driver chooses what to do with `ok=False` (warn, fail-soft, abort).
    """
    artifact_path = Path(artifact_path)

    try:
        last = task_call(agent, payload)
    except TaskError as e:
        last = {"status": "error", "reason": f"task_error:{e}"}

    artifact = verify_on_disk(artifact_path)
    if artifact is not None:
        return RetryResult(ok=True, attempts=1, last_result=last, artifact=artifact)

    retry_payload = dict(payload)
    retry_payload[payload_retry_key] = on_failure_prompt_suffix
    try:
        last = task_call(agent, retry_payload)
    except TaskError as e:
        last = {"status": "error", "reason": f"task_error:{e}"}

    artifact = verify_on_disk(artifact_path)
    return RetryResult(
        ok=artifact is not None,
        attempts=2,
        last_result=last,
        artifact=artifact,
    )


# ---------------------------------------------------------------------------
# Run-context + checkpoint
# ---------------------------------------------------------------------------


def build_run_context(
    *,
    project_root: str | Path,
    locale: str = "en",
    mode: str = "auto",
    categories: Optional[list[str]] = None,
    force_full: bool = False,
    interactive: bool = False,
    run_id: Optional[str] = None,
    now: Optional[str] = None,
) -> dict:
    """Build the RunContext dict and create on-disk directories.

    Side effects:
      - creates ``${project_root}/.qa-skills/checkpoints/``
      - creates ``${project_root}/.qa-skills/logs/${run_id}/``
      - creates ``${project_root}/test-reports/``

    Returns a dict with all paths absolute. Callers pass this dict through
    every phase.
    """
    project_root = Path(project_root).resolve()
    rid = run_id or str(uuid.uuid4())
    checkpoint_dir = project_root / ".qa-skills" / "checkpoints"
    logs_dir = project_root / ".qa-skills" / "logs" / rid
    reports_dir = project_root / "test-reports"

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    return {
        "run_id": rid,
        "project_root": str(project_root),
        "locale": locale,
        "mode": mode,
        "categories": list(categories) if categories else None,
        "force_full": bool(force_full),
        "interactive": bool(interactive),
        "checkpoint_dir": str(checkpoint_dir),
        "logs_dir": str(logs_dir),
        "reports_dir": str(reports_dir),
        "analysis_path": str(logs_dir / "analysis.json"),
        "strategy_path": str(logs_dir / "strategy.json"),
        "expected_files_path": str(logs_dir / "expected_files.json"),
        "state_path": str(project_root / "test-state.json"),
        "started_at": now or now_iso(),
    }


def write_checkpoint(
    rc: dict,
    *,
    phase: float | int,
    phase_name: str,
    completed: bool = False,
    extra: Optional[dict] = None,
) -> Path:
    """Write `<checkpoint_dir>/run.json` atomically.

    `phase` accepts floats (e.g. 2.5, 2.7) so callers can use the standard
    QA-Skills phase numbering.

    Carries forward `completed_skills[]` from any prior checkpoint so the
    list grows monotonically across phases.
    """
    path = Path(rc["checkpoint_dir"]) / "run.json"
    prior_skills: list[str] = []
    prior = verify_on_disk(path)
    if prior and isinstance(prior.get("completed_skills"), list):
        prior_skills = list(prior["completed_skills"])
    if phase_name not in prior_skills:
        prior_skills.append(phase_name)

    payload = {
        "run_id": rc["run_id"],
        "phase": phase,
        "phase_name": phase_name,
        "completed_skills": prior_skills,
        "started_at": rc.get("started_at", now_iso()),
        "updated_at": now_iso(),
        "completed": bool(completed),
    }
    if extra:
        payload.update(extra)

    atomic_write_json(path, payload)
    return path


def phase_checkpoint(rc: dict, phase: float | int, name: str) -> None:
    """One-liner used at the end of every phase. Never marks completed=True.

    Phase 9 (or driver shutdown) sets completed=True via `write_checkpoint`
    with `completed=True` explicitly.
    """
    write_checkpoint(rc, phase=phase, phase_name=name, completed=False)
