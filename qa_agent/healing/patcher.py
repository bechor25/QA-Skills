"""Snapshot / apply / revert primitives for the heal loop.

Rollback strategy is **per-file copy snapshots** under the run dir, not
git stash: the target project may not be a git repo, and stash would
entangle the user's own uncommitted work. This matches the codebase's
existing `runs/<run_id>/` scratch convention and atomic writes.

`heal-apply` snapshots a file before mutating it and records the snapshot
in `heal_journal.json`. An iteration that lowers the pass-rate is reverted
by restoring (or deleting) every file it snapshotted.

Edit scope is gated here (defence in depth — the agents are also told the
rules): tests, shared harness/helpers, framework configs, declared seed,
and `package.json` (deps) are writable; application source is not.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..shared.logging import get_logger
from ..shared.paths import run_dir
from ..state import schemas
from ..state.manager import StateManager

log = get_logger("qa_agent.healing.patcher")


class ScopeError(Exception):
    """Raised when a heal-apply target is outside the allowed edit scope."""


# ---------------------------------------------------------------------
# Edit-scope gate
# ---------------------------------------------------------------------

_ALLOWED_PREFIXES = (
    "tests/qa-agent/",
    "tests/",
    "test/",
)
_ALLOWED_BASENAMES = {
    "playwright.config.ts", "playwright.config.js", "playwright.config.mjs",
    "vitest.config.ts", "vitest.config.js", "vitest.config.mjs",
    "vite.config.ts", "vite.config.js",
    "jest.config.ts", "jest.config.js",
    "qa-agent.app.ts",
    "package.json",
}
_FORBIDDEN_SEGMENTS = ("/src/", "/app/src/", "/lib/")
_FORBIDDEN_TOP = ("src/", "app/", "lib/", "apps/")


def assert_in_scope(rel_path: str, kind: str, seed_targets: set[str] | None = None) -> None:
    """Raise ScopeError if `rel_path` may not be edited by the healer."""
    p = rel_path.replace("\\", "/").lstrip("./")
    seed_targets = seed_targets or set()

    if kind == "dep":  # handled via install_manager, not a file write
        return
    if p in seed_targets:
        return
    base = p.rsplit("/", 1)[-1]
    if any(p.startswith(pre) for pre in _ALLOWED_PREFIXES):
        return
    if base in _ALLOWED_BASENAMES:
        return
    if kind == "seed":
        # seed scripts often live outside tests/ — allow only when the
        # path clearly names a seed/fixture file, never bare app source.
        low = p.lower()
        if ("seed" in low or "fixture" in low) and not any(
            s in "/" + p for s in _FORBIDDEN_SEGMENTS
        ):
            return
    if any(p.startswith(t) for t in _FORBIDDEN_TOP) or any(
        s in "/" + p for s in _FORBIDDEN_SEGMENTS
    ):
        raise ScopeError(f"out-of-scope:app-source — {rel_path}")
    raise ScopeError(f"out-of-scope:unrecognized — {rel_path}")


# ---------------------------------------------------------------------
# Snapshots + journal
# ---------------------------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _flatten(rel_path: str) -> str:
    return rel_path.replace("\\", "/").strip("/").replace("/", "__")


def _journal_iter(journal: schemas.HealJournal, iteration: int, run_id: str) -> schemas.HealIterationJournal:
    for it in journal.iterations:
        if it.iteration == iteration:
            return it
    it = schemas.HealIterationJournal(
        iteration=iteration,
        run_id=run_id,
        started_at=datetime.now(timezone.utc),
    )
    journal.iterations.append(it)
    return it


def _snapshot(
    project_root: Path,
    rel_path: str,
    iteration: int,
    run_id: str,
    kind: str,
    cluster_id: str,
) -> schemas.HealFileSnapshot:
    target = project_root / rel_path
    snap_dir = run_dir(str(project_root), run_id) / "heal" / "snapshots" / f"iter{iteration}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / _flatten(rel_path)
    existed = target.exists()
    sha_before = ""
    if existed:
        shutil.copy2(target, snap_path)
        sha_before = _sha(target.read_text(encoding="utf-8", errors="ignore"))
    return schemas.HealFileSnapshot(
        path=rel_path,
        snapshot_path=str(snap_path),
        existed_before=existed,
        kind=kind,  # type: ignore[arg-type]
        cluster_id=cluster_id,
        sha_before=sha_before,
    )


# ---------------------------------------------------------------------
# Unified-diff / full-file apply
# ---------------------------------------------------------------------

def _looks_like_unified_diff(content: str) -> bool:
    head = content.lstrip()
    return head.startswith("--- ") or head.startswith("diff --git") or "\n@@ " in content


def _apply_unified_diff(original: str, diff: str) -> str:
    """Minimal unified-diff applier (single-file diffs, standard hunks).

    Raises ValueError if a hunk context does not match — the caller
    treats that as a failed apply and leaves the file untouched.
    """
    src = original.splitlines(keepends=False)
    out: list[str] = []
    si = 0
    lines = diff.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(("--- ", "+++ ", "diff --git", "index ")):
            i += 1
            continue
        if line.startswith("@@"):
            # @@ -l,s +l,s @@
            try:
                old_part = line.split(" ")[1]  # -l,s
                old_start = int(old_part[1:].split(",")[0]) - 1
            except (IndexError, ValueError) as e:
                raise ValueError(f"bad hunk header: {line}") from e
            out.extend(src[si:old_start])
            si = old_start
            i += 1
            while i < len(lines) and not lines[i].startswith("@@"):
                h = lines[i]
                if h.startswith("\\"):  # "\ No newline at end of file"
                    i += 1
                    continue
                tag, body = (h[0], h[1:]) if h else (" ", "")
                if tag == " ":
                    if si >= len(src) or src[si] != body:
                        raise ValueError("context mismatch")
                    out.append(src[si]); si += 1
                elif tag == "-":
                    if si >= len(src) or src[si] != body:
                        raise ValueError("delete mismatch")
                    si += 1
                elif tag == "+":
                    out.append(body)
                else:
                    raise ValueError(f"bad hunk line: {h!r}")
                i += 1
            continue
        i += 1
    out.extend(src[si:])
    trailing_nl = original.endswith("\n")
    return "\n".join(out) + ("\n" if trailing_nl else "")


def apply_patch(
    project_root: Path,
    sm: StateManager,
    rel_path: str,
    content: str,
    iteration: int,
    run_id: str,
    kind: str,
    cluster_id: str = "",
    seed_targets: set[str] | None = None,
) -> dict:
    """Snapshot `rel_path`, then apply `content` (full-file body or
    unified diff). Records the snapshot in `heal_journal.json`.
    Returns a small result dict for the CLI to print.
    """
    assert_in_scope(rel_path, kind, seed_targets)
    target = project_root / rel_path

    journal = sm.heal_journal()
    snap = _snapshot(project_root, rel_path, iteration, run_id, kind, cluster_id)

    if _looks_like_unified_diff(content):
        if not target.exists():
            raise ValueError(f"cannot apply diff — {rel_path} does not exist")
        original = target.read_text(encoding="utf-8", errors="ignore")
        new_text = _apply_unified_diff(original, content)
    else:
        new_text = content

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8")
    snap.sha_after = _sha(new_text)

    it = _journal_iter(journal, iteration, run_id)
    it.snapshots.append(snap)
    sm.save(journal)

    log.info("heal-apply: %s (%s, iter %d, cluster %s)",
             rel_path, kind, iteration, cluster_id or "-")
    return {
        "applied": True, "path": rel_path, "kind": kind,
        "iteration": iteration, "created": not snap.existed_before,
        "mode": "diff" if _looks_like_unified_diff(content) else "full",
    }


def revert_iteration(project_root: Path, sm: StateManager, iteration: int) -> dict:
    """Restore every file snapshotted in `iteration` (delete files that
    did not exist before). Marks the iteration reverted."""
    journal = sm.heal_journal()
    it = next((x for x in journal.iterations if x.iteration == iteration), None)
    if it is None:
        return {"reverted": False, "iteration": iteration, "reason": "no journal entry"}

    restored = 0
    for snap in reversed(it.snapshots):
        target = project_root / snap.path
        if snap.existed_before:
            sp = Path(snap.snapshot_path)
            if sp.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sp, target)
                restored += 1
        else:
            if target.exists():
                target.unlink()
                restored += 1
    it.reverted = True
    sm.save(journal)
    log.info("heal-apply: reverted iteration %d (%d files)", iteration, restored)
    return {"reverted": True, "iteration": iteration, "files": restored}
