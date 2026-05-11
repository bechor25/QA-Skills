"""Subprocess wrapper with timeout, capture, and kill-tree on cancel.

Every subprocess invocation in qa_agent goes through `run_subprocess`.
The wrapper:
  - enforces a timeout
  - captures stdout/stderr (size-bounded, tail-only)
  - kills the entire process group on timeout/cancel
  - emits a structured ProcessResult
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..shared.logging import get_logger

log = get_logger("qa_agent.runtime.process")

_MAX_BUFFER = 256 * 1024  # 256 KB tail kept per stream


@dataclass(slots=True)
class ProcessResult:
    cmd: list[str]
    cwd: str
    exit_code: int
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str
    timed_out: bool = False


def run_subprocess(
    cmd: list[str],
    cwd: str | Path,
    timeout: int,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run `cmd` and return a ProcessResult. Never raises on subprocess exit."""
    import time

    full_env = dict(os.environ)
    if env:
        full_env.update(env)

    start = time.monotonic()
    log.debug("exec: %s (cwd=%s, timeout=%ds)", " ".join(cmd), cwd, timeout)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError as e:
        return ProcessResult(
            cmd=cmd,
            cwd=str(cwd),
            exit_code=127,
            duration_seconds=0.0,
            stdout_tail="",
            stderr_tail=f"command not found: {e.filename}",
            timed_out=False,
        )

    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        exit_code = -1
        timed_out = True

    duration = round(time.monotonic() - start, 3)
    return ProcessResult(
        cmd=cmd,
        cwd=str(cwd),
        exit_code=exit_code,
        duration_seconds=duration,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
        timed_out=timed_out,
    )


def _kill_group(pid: int) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as e:  # noqa: BLE001
        log.warning("kill-tree failed for pid=%d: %s", pid, e)


def _tail(s: str | None) -> str:
    if not s:
        return ""
    if len(s) <= _MAX_BUFFER:
        return s
    return s[-_MAX_BUFFER:]
