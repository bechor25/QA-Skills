"""Scenario generator.

`build_baseline_scenarios` produces a deterministic Given/When/Then
scenario list from the strategy + KG. The output is what the LLM, when
present, gets to refine via the `prompts/scenario.md` contract.

`validate_llm_scenarios` accepts an LLM JSON and returns a clean
`Scenarios` pydantic model (raises StrategyError on contract violation).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..shared.errors import StrategyError
from ..shared.logging import get_logger
from ..state import schemas

log = get_logger("qa_agent.quality.scenario_generator")


# Per-category baseline templates. The generator inserts a feature noun
# (e.g. "auth") into {capability} placeholders.
_TEMPLATES: dict[str, list[dict]] = {
    "api": [
        {
            "title": "happy path: {capability}",
            "severity": "smoke",
            "steps": [
                ("given", "the service is running and the user is authenticated"),
                ("when", "the client calls the {capability} endpoint with valid input"),
                ("then", "the response is 2xx and the schema matches the contract"),
            ],
        },
        {
            "title": "validation: rejects bad input",
            "severity": "negative",
            "steps": [
                ("given", "the service is running"),
                ("when", "the client calls the {capability} endpoint with missing/invalid fields"),
                ("then", "the response is 4xx and explains the field error"),
            ],
        },
    ],
    "ui": [
        {
            "title": "user can navigate to {capability}",
            "severity": "smoke",
            "steps": [
                ("given", "the user is on the home page"),
                ("when", "the user navigates to the {capability} flow"),
                ("then", "the {capability} page renders without errors"),
            ],
        },
    ],
    "security": [
        {
            "title": "unauthenticated access is denied",
            "severity": "critical",
            "steps": [
                ("given", "no auth header is present"),
                ("when", "the client calls a protected {capability} endpoint"),
                ("then", "the response is 401/403 and no sensitive data leaks"),
            ],
        },
        {
            "title": "input is sanitized against injection",
            "severity": "critical",
            "steps": [
                ("given", "the service is running"),
                ("when", "the client sends an attempted SQL/command injection payload to {capability}"),
                ("then", "the payload is rejected or escaped and produces no execution"),
            ],
        },
    ],
    "accessibility": [
        {
            "title": "{capability} page meets WCAG 2.1 AA",
            "severity": "critical",
            "steps": [
                ("given", "the {capability} page is loaded"),
                ("when", "axe-core scans the rendered DOM"),
                ("then", "no critical or serious violations are reported"),
            ],
        }
    ],
    "performance": [
        {
            "title": "{capability} responds within budget",
            "severity": "smoke",
            "steps": [
                ("given", "the service is warm"),
                ("when", "the client issues 10 sequential calls to {capability}"),
                ("then", "p95 latency stays under the configured budget"),
            ],
        }
    ],
    "regression": [
        {
            "title": "previously-fixed bug stays fixed in {capability}",
            "severity": "critical",
            "steps": [
                ("given", "the last-known reproducer state is restored"),
                ("when", "the {capability} flow is replayed"),
                ("then", "the bug does not recur and the assertions still pass"),
            ],
        }
    ],
}


def build_baseline_scenarios(strategy: schemas.Strategy) -> schemas.Scenarios:
    """Deterministic scenarios from a Strategy."""
    out: list[schemas.Scenario] = []
    for s in strategy.entries:
        for cat in s.categories:
            for idx, tpl in enumerate(_TEMPLATES.get(cat, []), start=1):
                scenario_id = f"sc::{s.capability}::{cat}::{idx:02d}"
                steps = [
                    schemas.ScenarioStep(keyword=k, text=text.format(capability=s.capability))
                    for k, text in tpl["steps"]
                ]
                out.append(
                    schemas.Scenario(
                        id=scenario_id,
                        feature_id=s.feature_id or f"feat::{s.capability}",
                        capability=s.capability,
                        category=cat,
                        title=tpl["title"].format(capability=s.capability),
                        description="",
                        steps=steps,
                        severity=tpl["severity"],
                    )
                )

    log.info("scenarios: baseline generated %d scenarios", len(out))
    return schemas.Scenarios(built_at=datetime.now(timezone.utc), entries=out)


def validate_llm_scenarios(payload: Any, strategy: schemas.Strategy) -> schemas.Scenarios:
    """Validate LLM-produced scenarios; raise StrategyError on violations."""
    if not isinstance(payload, dict) or "entries" not in payload:
        raise StrategyError("scenarios payload must be an object with 'entries'")
    raw = payload["entries"]
    if not isinstance(raw, list) or not raw:
        raise StrategyError("scenarios.entries must be a non-empty list")

    known_capabilities = {s.capability for s in strategy.entries}
    allowed_categories: set[str] = set()
    for s in strategy.entries:
        allowed_categories.update(s.categories)
    allowed_severity = {"smoke", "critical", "edge", "negative"}

    out: list[schemas.Scenario] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StrategyError(f"scenarios.entries[{i}] must be an object")
        cap = item.get("capability")
        if cap not in known_capabilities:
            raise StrategyError(f"scenarios.entries[{i}].capability '{cap}' not in strategy")
        cat = item.get("category")
        if cat not in allowed_categories:
            raise StrategyError(f"scenarios.entries[{i}].category '{cat}' not in strategy categories")
        sev = item.get("severity", "smoke")
        if sev not in allowed_severity:
            raise StrategyError(f"scenarios.entries[{i}].severity '{sev}' invalid")
        sid = item.get("id") or f"sc::{cap}::{cat}::{i:02d}"
        if sid in seen_ids:
            raise StrategyError(f"scenarios.entries[{i}].id '{sid}' is duplicated")
        seen_ids.add(sid)

        steps_raw = item.get("steps") or []
        if not isinstance(steps_raw, list) or not steps_raw:
            raise StrategyError(f"scenarios.entries[{i}].steps must be non-empty")
        steps: list[schemas.ScenarioStep] = []
        for j, step in enumerate(steps_raw):
            if not isinstance(step, dict):
                raise StrategyError(f"scenarios[{i}].steps[{j}] must be an object")
            kw = step.get("keyword")
            if kw not in {"given", "when", "then", "and"}:
                raise StrategyError(f"scenarios[{i}].steps[{j}].keyword invalid")
            text = step.get("text") or ""
            if not text.strip():
                raise StrategyError(f"scenarios[{i}].steps[{j}].text empty")
            steps.append(schemas.ScenarioStep(keyword=kw, text=text))

        out.append(
            schemas.Scenario(
                id=sid,
                feature_id=item.get("feature_id") or f"feat::{cap}",
                capability=cap,
                category=cat,
                title=item.get("title") or sid,
                description=item.get("description") or "",
                steps=steps,
                severity=sev,
            )
        )

    log.info("scenarios: validated %d LLM scenarios", len(out))
    return schemas.Scenarios(built_at=datetime.now(timezone.utc), entries=out)
