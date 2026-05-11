"""Per-agent AgentResult persistence (Track B4).

Every Task call's return value should be persisted to
`${LOGS_DIR}/agent_output_<agent>.json` so a postmortem of a failed run can
inspect the exact sub-agent payload (status, outputs, missing_items,
warnings). When batching, the orchestrator writes both per-batch files and a
merged file so investigators can drill from summary to single-batch detail.

Layout:
    ${LOGS_DIR}/
      agent_output_qa-unit-test.json              # merged across batches
      agent_output_qa-unit-test_batch_000.json    # one per batch
      agent_output_qa-api-test.json
      ...

All writes are atomic (write-to-temp + rename). Stdlib only.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def agent_log_path(logs_dir: Path | str, agent: str, batch_idx: int | None = None) -> Path:
    base = Path(logs_dir)
    if batch_idx is None:
        return base / f"agent_output_{agent}.json"
    return base / f"agent_output_{agent}_batch_{batch_idx:03d}.json"


def write_agent_output(
    logs_dir: Path | str,
    agent: str,
    result: dict,
    batch_idx: int | None = None,
) -> Path:
    """Persist one Task return value to disk and return the path."""
    p = agent_log_path(logs_dir, agent, batch_idx)
    _atomic_write_json(p, result)
    return p


def write_merged_agent_output(
    logs_dir: Path | str,
    agent: str,
    results: list[dict],
) -> Path:
    """Aggregate per-batch results into a single merged payload.

    The merged shape mirrors a single AgentResult so downstream readers do not
    need batch awareness:
        {agent, status, outputs[], missing_items[], warnings[], batches[]}
    `status` collapses to the worst observed (error > partial > skipped > passed).
    """
    merged: dict[str, Any] = {
        "agent": agent,
        "status": "passed",
        "outputs": [],
        "missing_items": [],
        "warnings": [],
        "batches": [],
    }
    worst_rank = 0
    rank = {"passed": 0, "skipped": 1, "partial": 2, "error": 3}

    for i, r in enumerate(results or []):
        if not isinstance(r, dict):
            continue
        merged["batches"].append({"index": i, "status": r.get("status")})
        merged["outputs"].extend(r.get("outputs") or [])
        merged["missing_items"].extend(r.get("missing_items") or [])
        merged["warnings"].extend(r.get("warnings") or [])
        s = r.get("status") or "passed"
        rank_for = rank.get(s.split(":", 1)[0] if isinstance(s, str) else "passed", 1)
        if rank_for > worst_rank:
            worst_rank = rank_for

    merged["status"] = {0: "passed", 1: "skipped", 2: "partial", 3: "error"}[worst_rank]
    merged["missing_items"] = sorted(set(merged["missing_items"]))
    merged["warnings"]      = sorted(set(merged["warnings"]))

    p = agent_log_path(logs_dir, agent, batch_idx=None)
    _atomic_write_json(p, merged)
    return p


__all__ = [
    "agent_log_path",
    "write_agent_output",
    "write_merged_agent_output",
]


# CLI wrapper: skills/_shared/scripts/agent_log.py
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.agent_log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_write = sub.add_parser("write", help="Write one Task return value.")
    p_write.add_argument("--logs-dir", required=True)
    p_write.add_argument("--agent", required=True)
    p_write.add_argument("--batch-index", type=int, default=None)
    p_write.add_argument(
        "--json",
        required=False,
        help="Inline AgentResult JSON. If absent, reads from stdin.",
    )

    p_merge = sub.add_parser(
        "merge",
        help="Read all batch logs for an agent and write merged file.",
    )
    p_merge.add_argument("--logs-dir", required=True)
    p_merge.add_argument("--agent", required=True)

    args = parser.parse_args()

    if args.cmd == "write":
        raw = args.json if args.json is not None else sys.stdin.read()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(3)
        p = write_agent_output(args.logs_dir, args.agent, obj, batch_idx=args.batch_index)
        json.dump({"written": str(p)}, sys.stdout)
        sys.stdout.write("\n")
    elif args.cmd == "merge":
        logs_dir = Path(args.logs_dir)
        prefix = f"agent_output_{args.agent}_batch_"
        results = []
        for f in sorted(logs_dir.glob(f"{prefix}*.json")):
            try:
                results.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        p = write_merged_agent_output(logs_dir, args.agent, results)
        json.dump({"merged": str(p), "batches": len(results)}, sys.stdout)
        sys.stdout.write("\n")
