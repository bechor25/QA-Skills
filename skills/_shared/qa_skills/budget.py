"""Budget arithmetic + batch state for sub-agent dispatch (A5 + A5.b).

Each generated test file costs roughly 30-60s of LLM time. When `expected_files`
exceeds what fits in `per_agent_timeout_seconds`, the orchestrator MUST batch.
Otherwise a single sub-agent invocation runs out of time and the historical
fallback path emitted stub files for the remainder.

Two responsibilities:
  1. `estimate_fit` + `split_into_batches` — derive batch count + slices.
  2. `batch_state.json` persistence — record per-batch completion so a
     restarted orchestrator resumes from the first incomplete batch instead
     of regenerating from scratch.

All tunables are empirical, project-agnostic constants. Adding QA-Skills to
a new project must NEVER require editing this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

AVG_SECONDS_PER_FILE: int = 45               # empirical; project-agnostic
SAFETY_FACTOR: float = 0.7                   # accounts for fix-iterations + I/O
MAX_PARALLEL_BATCHES_PER_CATEGORY: int = 3   # rate-limit safe default


# ---------- A5: estimation & splitting ----------


def estimate_fit(files_count: int, timeout_seconds: int) -> tuple[int, int]:
    """Return (fits_per_batch, batch_count).

    Always at least 1 file per batch even on tiny timeouts.
    Empty input → (1, 0).
    """
    if files_count <= 0:
        return (1, 0)
    fits = max(1, int(timeout_seconds * SAFETY_FACTOR / AVG_SECONDS_PER_FILE))
    batches = (files_count + fits - 1) // fits
    return (fits, batches)


def split_into_batches(expected_files: list[Any], fits_per_batch: int) -> list[list[Any]]:
    """Slice expected_files into batches of at most fits_per_batch entries."""
    if fits_per_batch <= 0:
        raise ValueError("fits_per_batch must be >= 1")
    return [
        expected_files[i:i + fits_per_batch]
        for i in range(0, len(expected_files), fits_per_batch)
    ]


# ---------- A5.b: batch state, resume, parallel windows ----------


def batch_id(category: str, idx: int) -> str:
    """Stable ID for a (category, batch index) pair. Zero-padded for sort order."""
    return f"{category}:{idx:03d}"


def batch_state_path(logs_dir: Path) -> Path:
    return Path(logs_dir) / "batch_state.json"


def load_batch_state(logs_dir: Path) -> dict[str, dict[str, Any]]:
    """Load batch_state.json. Returns {} when absent or unreadable."""
    p = batch_state_path(logs_dir)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_batch_state(logs_dir: Path, state: dict[str, dict[str, Any]]) -> None:
    p = batch_state_path(logs_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def is_completed(state: dict[str, dict[str, Any]], bid: str) -> bool:
    entry = state.get(bid)
    return isinstance(entry, dict) and entry.get("status") == "completed"


def mark_completed(
    state: dict[str, dict[str, Any]],
    bid: str,
    output_paths: list[str],
) -> None:
    state[bid] = {"status": "completed", "outputs": list(output_paths)}


def pending_batches(
    state: dict[str, dict[str, Any]],
    category: str,
    batches: list[list[Any]],
) -> list[tuple[int, list[Any]]]:
    """Return [(idx, batch)] for batches NOT yet marked completed in state."""
    return [
        (i, b) for i, b in enumerate(batches)
        if not is_completed(state, batch_id(category, i))
    ]


def summarize_prior_batches(
    state: dict[str, dict[str, Any]],
    category: str,
) -> list[dict[str, Any]]:
    """Compact prior-batch summary for context-warm dispatch.

    Returns [{batch_id, paths[]}] — NO code content, just paths. Lets a later
    batch's sub-agent know what siblings already produced, without exploding
    the context window.
    """
    out: list[dict[str, Any]] = []
    prefix = f"{category}:"
    for bid in sorted(state.keys()):
        if not bid.startswith(prefix):
            continue
        info = state[bid]
        if isinstance(info, dict) and info.get("status") == "completed":
            out.append({"batch_id": bid, "paths": list(info.get("outputs", []))})
    return out


def chunked(seq: Iterable[Any], size: int) -> Iterable[list[Any]]:
    """Yield successive lists of length <= size from `seq`."""
    if size <= 0:
        raise ValueError("size must be >= 1")
    bucket: list[Any] = []
    for item in seq:
        bucket.append(item)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


__all__ = [
    "AVG_SECONDS_PER_FILE",
    "SAFETY_FACTOR",
    "MAX_PARALLEL_BATCHES_PER_CATEGORY",
    "estimate_fit",
    "split_into_batches",
    "batch_id",
    "batch_state_path",
    "load_batch_state",
    "save_batch_state",
    "is_completed",
    "mark_completed",
    "pending_batches",
    "summarize_prior_batches",
    "chunked",
]


# CLI wrapper: skills/_shared/scripts/budget.py
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.budget")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_est = sub.add_parser("estimate", help="Compute (fits_per_batch, batch_count).")
    p_est.add_argument("--files", type=int, required=True)
    p_est.add_argument("--timeout", type=int, required=True)

    p_pending = sub.add_parser(
        "pending",
        help="Report indices of pending batches for a category.",
    )
    p_pending.add_argument("--logs-dir", required=True)
    p_pending.add_argument("--category", required=True)
    p_pending.add_argument("--batch-count", type=int, required=True)

    p_mark = sub.add_parser("mark-completed", help="Mark a batch completed.")
    p_mark.add_argument("--logs-dir", required=True)
    p_mark.add_argument("--category", required=True)
    p_mark.add_argument("--index", type=int, required=True)
    p_mark.add_argument(
        "--paths",
        required=True,
        help="JSON array of emitted paths, e.g. '[\"tests/api/auth/test_login.py\"]'",
    )

    p_prior = sub.add_parser(
        "prior-summary",
        help="Emit compact prior-batches summary for a category.",
    )
    p_prior.add_argument("--logs-dir", required=True)
    p_prior.add_argument("--category", required=True)

    args = parser.parse_args()

    if args.cmd == "estimate":
        fits, batches = estimate_fit(args.files, args.timeout)
        json.dump({"fits_per_batch": fits, "batch_count": batches}, sys.stdout)
        sys.stdout.write("\n")
    elif args.cmd == "pending":
        state = load_batch_state(Path(args.logs_dir))
        idx = [
            i for i in range(args.batch_count)
            if not is_completed(state, batch_id(args.category, i))
        ]
        json.dump({"category": args.category, "pending_indices": idx}, sys.stdout)
        sys.stdout.write("\n")
    elif args.cmd == "mark-completed":
        state = load_batch_state(Path(args.logs_dir))
        paths_list = json.loads(args.paths)
        if not isinstance(paths_list, list):
            print("FAIL: --paths must be a JSON array", file=sys.stderr)
            sys.exit(2)
        mark_completed(state, batch_id(args.category, args.index), paths_list)
        save_batch_state(Path(args.logs_dir), state)
        json.dump({"ok": True, "batch_id": batch_id(args.category, args.index)}, sys.stdout)
        sys.stdout.write("\n")
    elif args.cmd == "prior-summary":
        state = load_batch_state(Path(args.logs_dir))
        json.dump(summarize_prior_batches(state, args.category), sys.stdout, indent=2)
        sys.stdout.write("\n")
