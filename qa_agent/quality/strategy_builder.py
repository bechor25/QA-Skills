"""Strategy builder.

Two entry points:

1. `build_baseline_strategy(risk, config)` — deterministic strategy built
   directly from the risk matrix. Used when `--no-llm` is set and as the
   prior the LLM must improve on, not replace.
2. `validate_llm_strategy(json_blob, risk)` — parses, normalizes, and
   gates an LLM-produced strategy JSON before it is persisted. Every
   entry must reference a real feature/capability from the risk matrix
   and may not invent categories outside the configured allowlist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..shared.errors import StrategyError
from ..shared.logging import get_logger
from ..state import schemas

log = get_logger("qa_agent.quality.strategy_builder")


# Allowed categories — matches `configs/defaults.yaml`.
ALLOWED_CATEGORIES: set[str] = {"api", "ui", "security", "accessibility", "performance", "regression"}

# Default category packs by capability — what we'd recommend without any
# LLM input. The LLM may prune or extend (with validation).
_DEFAULT_PACKS: dict[str, list[str]] = {
    "auth":        ["api", "ui", "security"],
    "payments":    ["api", "ui", "security", "regression"],
    "permissions": ["api", "security"],
    "user-mgmt":   ["api", "ui"],
    "data-export": ["api", "security", "performance"],
    "file-upload": ["api", "security"],
    "search":      ["api", "performance"],
    "admin":       ["api", "ui", "security"],
    "api-public":  ["api", "accessibility"],
    "other":       ["api"],
}


def build_baseline_strategy(
    risk: schemas.RiskMatrix,
    allowed_categories: set[str] | None = None,
) -> schemas.Strategy:
    """Deterministic strategy: high-risk capabilities get richer packs."""
    allowed = allowed_categories or ALLOWED_CATEGORIES
    entries: list[schemas.StrategyEntry] = []

    for risk_entry in risk.entries:
        pack = list(_DEFAULT_PACKS.get(risk_entry.capability, ["api"]))
        # Add UI and accessibility for very high-risk surfaces if not present.
        if risk_entry.score >= 25.0 and "ui" not in pack:
            pack.append("ui")
        if risk_entry.score >= 30.0 and "accessibility" not in pack:
            pack.append("accessibility")
        # Drop anything outside the allowlist.
        pack = [c for c in pack if c in allowed]
        priority = _bucket_priority(risk_entry.score)
        entries.append(
            schemas.StrategyEntry(
                capability=risk_entry.capability,
                feature_id=risk_entry.feature_id,
                categories=pack,
                priority=priority,
                rationale=f"baseline pack for {risk_entry.capability}, score={risk_entry.score}",
            )
        )

    log.info("strategy: baseline produced %d entries", len(entries))
    return schemas.Strategy(built_at=datetime.now(timezone.utc), entries=entries)


def validate_llm_strategy(
    payload: Any,
    risk: schemas.RiskMatrix,
    allowed_categories: set[str] | None = None,
) -> schemas.Strategy:
    """Validate an LLM-produced strategy JSON. Raises StrategyError on any
    contract violation; returns a clean pydantic Strategy on success.

    The accepted shape is:

        { "entries": [ { "capability", "feature_id"?, "categories": [..],
                         "priority": 0..10, "rationale": str }, ... ] }
    """
    allowed = allowed_categories or ALLOWED_CATEGORIES
    if not isinstance(payload, dict) or "entries" not in payload:
        raise StrategyError("strategy payload must be an object with 'entries'")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise StrategyError("strategy.entries must be a non-empty list")

    known_capabilities = {e.capability for e in risk.entries}
    known_features = {e.feature_id for e in risk.entries if e.feature_id}

    out: list[schemas.StrategyEntry] = []
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise StrategyError(f"entries[{i}] must be an object")
        cap = raw.get("capability")
        if cap not in known_capabilities:
            raise StrategyError(f"entries[{i}].capability '{cap}' not in risk matrix")
        feat = raw.get("feature_id")
        if feat is not None and feat not in known_features:
            raise StrategyError(f"entries[{i}].feature_id '{feat}' not in risk matrix")
        cats = raw.get("categories") or []
        if not isinstance(cats, list):
            raise StrategyError(f"entries[{i}].categories must be a list")
        bad = [c for c in cats if c not in allowed]
        if bad:
            raise StrategyError(f"entries[{i}].categories contains disallowed: {bad}")
        priority = raw.get("priority", 5)
        if not isinstance(priority, int) or not (0 <= priority <= 10):
            raise StrategyError(f"entries[{i}].priority must be int in 0..10")
        rationale = raw.get("rationale") or ""
        out.append(
            schemas.StrategyEntry(
                capability=cap,
                feature_id=feat,
                categories=cats,
                priority=priority,
                rationale=str(rationale),
            )
        )

    log.info("strategy: validated %d LLM entries", len(out))
    return schemas.Strategy(built_at=datetime.now(timezone.utc), entries=out)


def _bucket_priority(score: float) -> int:
    if score >= 35.0:
        return 10
    if score >= 28.0:
        return 8
    if score >= 20.0:
        return 6
    if score >= 12.0:
        return 4
    return 2
