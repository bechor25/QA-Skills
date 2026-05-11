"""ServerPlan builder + reachability/start helpers.

Stdlib-only. No requests/httpx dependencies — uses urllib.
Sub-agents must NOT call this. Orchestrator builds the plan and passes it down.
"""

from __future__ import annotations

import os
import shlex
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

from .types import Analysis, ServerPlan


def _url_from_port(port: int | None) -> str | None:
    return f"http://localhost:{port}" if port else None


def build_server_plan(
    analysis: Analysis,
    mode: str = "auto",
    allow_start_explicit: bool | None = None,
    timeout_seconds: int = 30,
) -> ServerPlan:
    """Construct a ServerPlan from analysis.server_hint + frontend/backend dev_server.

    `mode` ∈ {"auto","interactive"}.
    `allow_start_explicit` overrides the default (False); interactive mode may flip it
    after the orchestrator asks the user.
    """
    hint = analysis.server_hint
    kind = analysis.frontend_kind

    url = (
        analysis.frontend_dev_server
        or analysis.backend_dev_server
        or (_url_from_port(hint.frontend_port) if hint else None)
        or (_url_from_port(hint.backend_port) if hint else None)
    )

    start_command: str | None = None
    if hint:
        if kind == "spa":
            start_command = hint.frontend_command or hint.backend_command
        elif kind in ("ssr", "mixed"):
            start_command = hint.backend_command or hint.frontend_command
        else:
            start_command = None

    if allow_start_explicit is True:
        start_allowed = True
    elif allow_start_explicit is False:
        start_allowed = False
    else:
        start_allowed = False  # default: never auto-start without explicit consent

    return ServerPlan(
        url=url,
        start_command=start_command,
        start_allowed=start_allowed,
        timeout_seconds=timeout_seconds,
        cleanup_pid=None,
    )


def is_reachable(url: str, timeout: float = 5.0) -> bool:
    """Treat any HTTP response (incl. 4xx/5xx) as 'reachable' — server is up.

    Only timeouts / connection-refused mean 'unreachable'.
    """
    try:
        urllib.request.urlopen(url, timeout=timeout)  # 2xx/3xx
        return True
    except urllib.error.HTTPError:
        return True   # server responded
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return False


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_server(plan: ServerPlan) -> ServerPlan:
    """Background-spawn `plan.start_command`. Poll `plan.url` until reachable.

    Returns a new ServerPlan with cleanup_pid populated. Raises RuntimeError on timeout.
    Caller is responsible for invoking stop_server() at run end.
    """
    if not plan.start_allowed:
        raise RuntimeError("server start not allowed by plan")
    if not plan.start_command:
        raise RuntimeError("no start_command in plan")
    if not plan.url:
        raise RuntimeError("no url in plan")

    proc = subprocess.Popen(  # noqa: S603 — input is validated string from analyzer
        shlex.split(plan.start_command),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + plan.timeout_seconds
    while time.monotonic() < deadline:
        if is_reachable(plan.url, timeout=1.5):
            return ServerPlan(
                url=plan.url,
                start_command=plan.start_command,
                start_allowed=plan.start_allowed,
                timeout_seconds=plan.timeout_seconds,
                cleanup_pid=proc.pid,
            )
        time.sleep(0.5)

    # timeout — kill spawn and raise
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    raise RuntimeError(f"server did not become reachable at {plan.url} within {plan.timeout_seconds}s")


def stop_server(plan: ServerPlan) -> bool:
    """Kill the process group spawned by start_server. Idempotent."""
    if plan.cleanup_pid is None:
        return False
    try:
        os.killpg(os.getpgid(plan.cleanup_pid), signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False


__all__ = [
    "build_server_plan",
    "is_reachable",
    "start_server",
    "stop_server",
]
