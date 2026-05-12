"""Scaffold builders — emit thin, agent-authoring-ready test stubs.

Each scaffold contains:
  - the imports and harness wiring the runner needs to execute the file
  - a `describe`/test block with a placeholder body (`it.todo` /
    `pytest.skip`) and a stable scenario marker comment

The qa-body-author sub-agent is expected to replace the placeholder
with a real test body authored from the scenario + contract.

Scaffolds are intentionally inert: if no sub-agent runs, the runner
sees zero authored tests and reports the gap rather than emitting
false greens.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..state import schemas
from .base import GeneratedFile, slugify


SCAFFOLD_MARKER = "QA-AGENT-BODY"
"""Token a body author must remove when filling a stub."""


@dataclass(slots=True)
class ScaffoldHints:
    """Optional hooks the body author can wire in."""

    fixture_import: str = ""
    fixture_setup: str = ""
    fixture_teardown: str = ""

    @classmethod
    def from_plan(cls, plan: schemas.TestDataPlan | None) -> "ScaffoldHints":
        if plan is None or plan.strategy == "none":
            return cls()
        return cls(
            fixture_import=plan.helper_import,
            fixture_setup=plan.setup_call,
            fixture_teardown=plan.teardown_call,
        )


# ---------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------

def emit_scaffold(
    scenario_id: str,
    capability: str,
    category: str,
    title: str,
    language: str,
    framework_hint: str | None = None,
    hints: ScaffoldHints | None = None,
) -> GeneratedFile:
    """Return a single scaffold file for one scenario.

    `framework_hint` overrides the default per-category framework
    (e.g. force `playwright` for UI even if jest is available).
    """
    hints = hints or ScaffoldHints()

    if category == "api":
        if language == "python":
            return _api_pytest(scenario_id, capability, title, hints)
        return _api_jest(scenario_id, capability, title, hints)

    if category == "ui":
        if language == "python":
            return _ui_pytest_playwright(scenario_id, capability, title, hints)
        return _ui_playwright_ts(scenario_id, capability, title, hints)

    if category == "security":
        if language == "python":
            return _security_pytest(scenario_id, capability, title, hints)
        return _security_jest(scenario_id, capability, title, hints)

    if category == "accessibility":
        return _a11y_playwright_ts(scenario_id, capability, title, hints)

    if category == "performance":
        if language == "python":
            return _perf_pytest(scenario_id, capability, title, hints)
        return _perf_jest(scenario_id, capability, title, hints)

    # regression — fall back to api shape
    if language == "python":
        return _api_pytest(scenario_id, capability, title, hints)
    return _api_jest(scenario_id, capability, title, hints)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _ts_header(scenario_id: str, capability: str, title: str) -> str:
    return (
        f"/* SCAFFOLD scenario={scenario_id} capability={capability} */\n"
        f"/* CONTRACT_PATH .qa-agent/state/contracts/{capability}.json */\n"
        f"/* SCENARIO_PATH .qa-agent/state/scenarios/{capability}.json */\n"
    )


def _py_header(scenario_id: str, capability: str, title: str) -> str:
    return (
        f'"""SCAFFOLD scenario={scenario_id} capability={capability}\n'
        f'\n'
        f'CONTRACT_PATH .qa-agent/state/contracts/{capability}.json\n'
        f'SCENARIO_PATH .qa-agent/state/scenarios/{capability}.json\n'
        f'"""\n'
    )


def _ts_fixture_block(hints: ScaffoldHints) -> tuple[str, str, str]:
    """Return (import_line, setup_line, teardown_line) for jest scaffolds."""
    imp = (hints.fixture_import + "\n") if hints.fixture_import else ""
    setup = f"    {hints.fixture_setup};\n" if hints.fixture_setup else ""
    teardown = f"    {hints.fixture_teardown};\n" if hints.fixture_teardown else ""
    return imp, setup, teardown


# ---------------------------------------------------------------------
# API scaffolds
# ---------------------------------------------------------------------

def _api_jest(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/api/{capability}.{slug}.spec.ts"
    fx_import, fx_setup, fx_teardown = _ts_fixture_block(hints)
    body = f'''{_ts_header(scenario_id, capability, title)}import request from "supertest";
import {{ describe, it, expect, beforeEach, afterEach }} from "@jest/globals";
import app from "../../../qa-agent.app";
{fx_import}
describe("{capability} — {title}", () => {{
  beforeEach(async () => {{
{fx_setup}  }});
  afterEach(async () => {{
{fx_teardown}  }});

  it.todo("{SCAFFOLD_MARKER}: author body from contract + scenario {scenario_id}");
}});
'''
    return GeneratedFile(rel_path=rel, body=body, framework="jest", language="typescript")


def _api_pytest(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/api/test_{capability}_{slug}.py"
    fixture_block = ""
    if hints.fixture_setup or hints.fixture_teardown:
        fixture_block = (
            "\n@pytest.fixture(autouse=True)\n"
            "def _qa_fixture():\n"
            f"    {hints.fixture_setup or 'pass'}\n"
            "    yield\n"
            f"    {hints.fixture_teardown or 'pass'}\n"
        )
    body = f'''{_py_header(scenario_id, capability, title)}import pytest

{hints.fixture_import}
{fixture_block}

@pytest.mark.qa_agent
def test_{slugify(title).replace("-", "_")}(api_client):
    pytest.skip("{SCAFFOLD_MARKER}: author body from contract + scenario {scenario_id}")
'''
    return GeneratedFile(rel_path=rel, body=body, framework="pytest", language="python")


# ---------------------------------------------------------------------
# UI scaffolds (Playwright)
# ---------------------------------------------------------------------

def _ui_playwright_ts(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/ui/{capability}.{slug}.spec.ts"
    body = f'''{_ts_header(scenario_id, capability, title)}import {{ test, expect }} from "@playwright/test";
{hints.fixture_import}

test("{capability} — {title}", async ({{ page }}) => {{
  test.fixme(true, "{SCAFFOLD_MARKER}: author body from contract + scenario {scenario_id}. " +
                  "Use selectors from .qa-agent/state/ui_selectors.json.");
}});
'''
    return GeneratedFile(rel_path=rel, body=body, framework="playwright", language="typescript")


def _ui_pytest_playwright(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/ui/test_{capability}_{slug}.py"
    body = f'''{_py_header(scenario_id, capability, title)}import pytest

{hints.fixture_import}

@pytest.mark.qa_agent
def test_{slug.replace("-", "_")}(page):
    pytest.skip("{SCAFFOLD_MARKER}: author body from contract + scenario {scenario_id}. "
                "Use selectors from .qa-agent/state/ui_selectors.json.")
'''
    return GeneratedFile(rel_path=rel, body=body, framework="playwright", language="python")


# ---------------------------------------------------------------------
# Security scaffolds
# ---------------------------------------------------------------------

def _security_jest(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/security/{capability}.{slug}.spec.ts"
    fx_import, fx_setup, fx_teardown = _ts_fixture_block(hints)
    body = f'''{_ts_header(scenario_id, capability, title)}import request from "supertest";
import {{ describe, it, expect, beforeEach, afterEach }} from "@jest/globals";
import app from "../../../qa-agent.app";
{fx_import}
describe("security — {capability} — {title}", () => {{
  beforeEach(async () => {{
{fx_setup}  }});
  afterEach(async () => {{
{fx_teardown}  }});

  it.todo("{SCAFFOLD_MARKER}: assert NEGATIVE outcome for scenario {scenario_id}");
}});
'''
    return GeneratedFile(rel_path=rel, body=body, framework="jest", language="typescript")


def _security_pytest(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/security/test_{capability}_{slug}.py"
    body = f'''{_py_header(scenario_id, capability, title)}import pytest

{hints.fixture_import}

@pytest.mark.qa_agent
@pytest.mark.security
def test_{slug.replace("-", "_")}(api_client):
    pytest.skip("{SCAFFOLD_MARKER}: assert NEGATIVE outcome for scenario {scenario_id}")
'''
    return GeneratedFile(rel_path=rel, body=body, framework="pytest", language="python")


# ---------------------------------------------------------------------
# Accessibility scaffold (Playwright + axe)
# ---------------------------------------------------------------------

def _a11y_playwright_ts(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/accessibility/{capability}.{slug}.spec.ts"
    body = f'''{_ts_header(scenario_id, capability, title)}import {{ test, expect }} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("a11y — {capability} — {title}", async ({{ page }}) => {{
  test.fixme(true, "{SCAFFOLD_MARKER}: run AxeBuilder for scenario {scenario_id}; assert zero serious/critical violations.");
}});
'''
    return GeneratedFile(rel_path=rel, body=body, framework="playwright", language="typescript")


# ---------------------------------------------------------------------
# Performance scaffolds
# ---------------------------------------------------------------------

def _perf_jest(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/performance/{capability}.{slug}.spec.ts"
    body = f'''{_ts_header(scenario_id, capability, title)}import request from "supertest";
import {{ describe, it, expect }} from "@jest/globals";
import app from "../../../qa-agent.app";

describe("perf — {capability} — {title}", () => {{
  it.todo("{SCAFFOLD_MARKER}: measure p95 over N requests for scenario {scenario_id}");
}});
'''
    return GeneratedFile(rel_path=rel, body=body, framework="jest", language="typescript")


def _perf_pytest(scenario_id: str, capability: str, title: str, hints: ScaffoldHints) -> GeneratedFile:
    slug = slugify(title)
    rel = f"tests/qa-agent/performance/test_{capability}_{slug}.py"
    body = f'''{_py_header(scenario_id, capability, title)}import pytest

@pytest.mark.qa_agent
@pytest.mark.performance
def test_{slug.replace("-", "_")}(api_client, benchmark):
    pytest.skip("{SCAFFOLD_MARKER}: measure p95 over N requests for scenario {scenario_id}")
'''
    return GeneratedFile(rel_path=rel, body=body, framework="pytest", language="python")
