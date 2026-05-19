"""`qa-agent heal-apply` — apply a scoped fix (or revert an iteration).

Apply mode: snapshot the target, then write a full-file body or apply a
unified diff. Scope-gated — application source is hard-rejected.
Revert mode: restore every file the given iteration snapshotted.
`--kind dep`: route to install_manager (no hand-edited lockfiles).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ...healing.patcher import ScopeError, apply_patch, revert_iteration
from ...runtime.install_manager import run_installs
from ...runtime.install_planner import InstallStep
from ...runtime.workspace import latest_run_id
from ...shared.logging import get_logger
from ...shared.paths import project_root
from ...state import schemas
from ...state.manager import StateManager

log = get_logger("qa_agent.heal_apply")


def _seed_targets(sm: StateManager) -> set[str]:
    plan = sm.load(schemas.TestDataPlan)
    out: set[str] = set()
    for blob in (plan.helper_import, plan.setup_call, plan.teardown_call):
        for tok in blob.replace("'", '"').split('"'):
            if "/" in tok and ("seed" in tok.lower() or "fixture" in tok.lower()):
                out.add(tok.lstrip("./"))
    return out


def run(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    sm = StateManager(args.project)

    if args.revert is not None:
        result = revert_iteration(root, sm, args.revert)
        print(json.dumps(result, indent=2))
        return 0 if result.get("reverted") else 1

    if args.kind == "dep":
        if not args.dep:
            log.error("heal-apply: --kind dep requires --dep '<manager> <pkg...>'")
            return 1
        parts = args.dep.split()
        step = InstallStep(manager=parts[0], args=parts[1:], reason="heal: missing dep")
        run_id = latest_run_id(args.project) or "heal"
        res = run_installs(root, [step], run_id)
        ok = all(r.exit_code == 0 for r in res)
        print(json.dumps({"applied": ok, "kind": "dep", "dep": args.dep}, indent=2))
        return 0 if ok else 1

    if not args.target:
        log.error("heal-apply: --target is required for kind=%s", args.kind)
        return 1
    content = sys.stdin.read() if args.patch in ("-", None) else Path(args.patch).read_text(encoding="utf-8")
    if not content.strip():
        log.error("heal-apply: empty patch/body")
        return 1

    try:
        result = apply_patch(
            root, sm,
            rel_path=args.target,
            content=content,
            iteration=args.iteration,
            run_id=latest_run_id(args.project) or "heal",
            kind=args.kind,
            cluster_id=args.cluster_id or "",
            seed_targets=_seed_targets(sm),
        )
    except ScopeError as e:
        print(json.dumps({"applied": False, "reason": str(e)}, indent=2))
        log.error("heal-apply: %s", e)
        return 2
    except ValueError as e:
        print(json.dumps({"applied": False, "reason": f"patch-failed: {e}"}, indent=2))
        log.error("heal-apply: patch failed on %s: %s", args.target, e)
        return 1

    print(json.dumps(result, indent=2))
    return 0
