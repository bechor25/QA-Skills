"""Root-cause clustering for the heal pipeline.

`heal-diagnose` runs the failed scope and hands the raw PerTestRecords
here. We collapse N failures into a handful of root causes so the
ops-diagnostician can apply ONE shared fix (Session-2 evidence: ~3
shared fixes unblocked ~130 tests) instead of fanning out per test.

A cluster is **systemic** when many failures share a signature *and* a
shared signal points at a single harness/config/seed/dep fix. Everything
else falls through as a **per_test** cluster — the long tail the Tier-2
fan-out handles. Prod-bug clusters (the app violating its own contract)
are flagged and never auto-fixed, so reporting them cannot inflate the
score.

This module reuses `classifiers.classify_failure` unchanged and adds a
declarative shared-signal rule table in the same style as
`classifiers._PATTERNS`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Callable, Iterable

from ..executors.base import PerTestRecord, extract_scenario_id
from ..state import schemas
from ..state.manager import StateManager
from .classifiers import FailureCategory, classify_failure

# ---------------------------------------------------------------------
# Signature normalization — turn "Expected 200, got 401 at auth.spec.ts:42:7"
# into a stable bucket key so 45 copies of the same failure collapse to 1.
# ---------------------------------------------------------------------

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_HEX_RE = re.compile(r"\b0x[0-9a-f]+\b", re.I)
_NUM_RE = re.compile(r"\d+")
_LINECOL_RE = re.compile(r":\d+:\d+")
_WS_RE = re.compile(r"\s+")
_ABS_PATH_RE = re.compile(r"(/[^\s:'\"]+)+")


def _normalize(error_message: str, error_stack: str) -> str:
    """Collapse volatile tokens so equivalent failures share a key."""
    head = (error_message or "").strip()
    if not head and error_stack:
        head = error_stack.strip().splitlines()[0] if error_stack.strip() else ""
    s = head[:400]
    s = _LINECOL_RE.sub(":#:#", s)
    s = _UUID_RE.sub("<uuid>", s)
    s = _HEX_RE.sub("<hex>", s)
    s = _ABS_PATH_RE.sub("<path>", s)
    s = _NUM_RE.sub("#", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    return s[:200]


# ---------------------------------------------------------------------
# Shared-signal rules — first match wins, mirrors classifiers._PATTERNS.
# A rule maps a (text -> bool) predicate to a shared signal + fix kind.
# Extend by appending here; the bucketing loop never changes.
# ---------------------------------------------------------------------

_FK_SEED_RE = re.compile(
    r"foreign key|violates|not null|no rows|record to (?:update|delete) does not exist|"
    r"prisma|does not exist in|seed|persona|@(?:ats|example)\.(?:dev|com)",
    re.IGNORECASE,
)
_CONFIG_RE = re.compile(
    r"baseurl|econnrefused|connect econnrefused|address already in use|"
    r"playwright config|vitest|storagestate|globalsetup|port \d+",
    re.IGNORECASE,
)
_HARNESS_IMPORT_RE = re.compile(
    r"cannot find module\s+['\"][^'\"]*(?:helpers?|fixtures?|setup|support)[^'\"]*['\"]|"
    r"is not a function.*fixture|cannot read propert.*\b(tokens?|fx)\b",
    re.IGNORECASE,
)
_DEP_RE = re.compile(
    r"cannot find module\s+['\"][^.\/'\"]|modulenotfounderror|"
    r"command not found|is not recognized as",
    re.IGNORECASE,
)
_PRODBUG_RE = re.compile(
    r"\b50\d\b|internal server error|unhandled|sendsuccess|"
    r"contract violation|envelope mismatch",
    re.IGNORECASE,
)

# (predicate, shared_signal, fix_kind)
_SHARED_SIGNAL_RULES: list[tuple[Callable[[str, FailureCategory], bool], str, str]] = [
    (lambda t, c: c == "auth", "auth-storage-state", "harness"),
    (lambda t, c: bool(_HARNESS_IMPORT_RE.search(t)), "missing-import", "harness"),
    (lambda t, c: bool(_FK_SEED_RE.search(t)), "db-seed", "seed"),
    (lambda t, c: c == "missing-dependency" or bool(_DEP_RE.search(t)), "missing-dep", "dep"),
    (lambda t, c: bool(_CONFIG_RE.search(t)), "config", "config"),
]

_SYSTEMIC_FIX_KINDS = {"harness", "config", "seed", "dep"}
_MIN_SYSTEMIC_SIZE = 2


def _shared_signal(text: str, cat: FailureCategory) -> tuple[str, str]:
    """Return (shared_signal, fix_kind) or ("", "unknown")."""
    for pred, signal, kind in _SHARED_SIGNAL_RULES:
        if pred(text, cat):
            return signal, kind
    return "", "unknown"


def _short_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:8]


def _is_prod_bug(text: str, sm: StateManager, test_id: str) -> bool:
    """Triage verdict wins when present (Session-2 had none — fall back
    to a log-signature heuristic so the honesty path works regardless).
    """
    v = sm.load_triage(test_id)
    if v is not None:
        return v.verdict == "prod-bug"
    return bool(_PRODBUG_RE.search(text))


def to_failure_records(
    records: Iterable[PerTestRecord],
    path_to_scenario: dict[str, str] | None = None,
) -> list[schemas.HealFailureRecord]:
    """Project executor PerTestRecords into persisted HealFailureRecords
    (only the failing/timed-out/errored ones)."""
    path_to_scenario = path_to_scenario or {}
    out: list[schemas.HealFailureRecord] = []
    for r in records:
        if r.status in {"passed", "skipped"}:
            continue
        text = f"{r.error_message}\n{r.error_stack}"
        scenario_id = (
            extract_scenario_id(r.test_id)
            or extract_scenario_id(r.title)
            or path_to_scenario.get(r.file, "")
        )
        out.append(
            schemas.HealFailureRecord(
                test_id=r.test_id,
                test_path=r.file,
                scenario_id=scenario_id,
                status=r.status,
                error_message=r.error_message,
                error_stack=r.error_stack,
                normalized_signature=_normalize(r.error_message, r.error_stack),
                failure_category=classify_failure(text),
            )
        )
    return out


def cluster_failures(
    failures: list[schemas.HealFailureRecord],
    sm: StateManager,
    run_id: str = "",
) -> schemas.HealClusters:
    """Group HealFailureRecords into systemic vs per_test clusters.

    Mutates each record's ``cluster_id`` in place so the caller can
    persist `heal_failures.json` with back-references.
    """
    groups: dict[tuple[str, str, str], list[schemas.HealFailureRecord]] = {}
    for f in failures:
        cat = f.failure_category or "unknown"
        text = f"{f.error_message}\n{f.error_stack}"
        signal, _ = _shared_signal(text, cat)  # type: ignore[arg-type]
        key = (cat, f.normalized_signature, signal)
        groups.setdefault(key, []).append(f)

    systemic: list[schemas.HealCluster] = []
    per_test: list[schemas.HealCluster] = []

    for (cat, sig, signal), members in groups.items():
        sample_text = f"{members[0].error_message}\n{members[0].error_stack}"
        _, fix_kind = _shared_signal(sample_text, cat)  # type: ignore[arg-type]
        prod = any(_is_prod_bug(f"{m.error_message}\n{m.error_stack}", sm, m.test_id)
                   for m in members)
        cid = f"{cat}-{_short_hash(sig + signal)}"
        is_systemic = (
            not prod
            and len(members) >= _MIN_SYSTEMIC_SIZE
            and bool(signal)
            and fix_kind in _SYSTEMIC_FIX_KINDS
        )
        for m in members:
            m.cluster_id = cid if is_systemic else f"{cid}-{_short_hash(m.test_id)}"

        if is_systemic:
            systemic.append(schemas.HealCluster(
                cluster_id=cid,
                tier="systemic",
                category=cat,
                signature=sig,
                member_test_ids=[m.test_id for m in members],
                member_paths=sorted({m.test_path for m in members if m.test_path}),
                shared_signal=signal,
                suggested_fix_kind=fix_kind,  # type: ignore[arg-type]
                suggested_target=_suggest_target(signal),
                size=len(members),
                is_prod_bug=False,
                rationale=f"{len(members)} failures share signal '{signal}' "
                          f"({cat}) — one {fix_kind} fix unblocks all.",
            ))
        else:
            for m in members:
                per_test.append(schemas.HealCluster(
                    cluster_id=m.cluster_id,
                    tier="per_test",
                    category=cat,
                    signature=sig,
                    member_test_ids=[m.test_id],
                    member_paths=[m.test_path] if m.test_path else [],
                    shared_signal=signal,
                    suggested_fix_kind="test",
                    size=1,
                    is_prod_bug=prod,
                    rationale="prod-bug — reported, not fixed" if prod
                              else "per-test residue",
                ))

    systemic.sort(key=lambda c: c.size, reverse=True)
    return schemas.HealClusters(
        built_at=datetime.now(timezone.utc),
        run_id=run_id,
        systemic=systemic,
        per_test=per_test,
    )


def _suggest_target(signal: str) -> str:
    return {
        "auth-storage-state": "tests/qa-agent/global-setup.ts",
        "missing-import": "tests/qa-agent/helpers/",
        "db-seed": "tests/qa-agent/global-db-seed.ts",
        "config": "playwright.config.ts / vitest.config.ts",
        "missing-dep": "package.json",
    }.get(signal, "")
