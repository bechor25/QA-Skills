"""Scaffold builders — emit grouped, agent-authoring-ready test files.

Each scaffold file groups every scenario for a single `(capability,
category)` into one test file with N stub blocks. The qa-body-author
sub-agent then replaces each stub with a real test body, keyed by
scenario_id.

Marker format inside each stub:
  ``QA-AGENT-BODY :: <scenario_id> :: <title>``

Body author finds the line by scenario_id, replaces the stub block,
keeps the file structure intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..state import schemas
from .base import GeneratedFile, slugify


SCAFFOLD_MARKER = "QA-AGENT-BODY"


@dataclass(slots=True)
class ScenarioStub:
    """Minimal scenario shape needed by the grouper."""
    id: str
    title: str


@dataclass(slots=True)
class ScaffoldHints:
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
# Public dispatchers
# ---------------------------------------------------------------------

def emit_scaffold_group(
    capability: str,
    category: str,
    scenarios: Sequence[ScenarioStub],
    language: str,
    framework_hint: str | None = None,
    hints: ScaffoldHints | None = None,
) -> GeneratedFile:
    """Return a single scaffold file holding stubs for every scenario
    in `(capability, category)`.
    """
    if not scenarios:
        raise ValueError("emit_scaffold_group: scenarios must be non-empty")
    hints = hints or ScaffoldHints()

    builder = _GROUP_BUILDERS.get((category, language))
    if builder is None:
        # Fall back by category, defaulting to api shape if exotic.
        builder = _GROUP_BUILDERS.get((category, "typescript")) or _api_jest_group
        if language == "python":
            builder = _GROUP_BUILDERS.get(("api", "python"), _api_pytest_group)
    return builder(capability, scenarios, hints)


def emit_scaffold(
    scenario_id: str,
    capability: str,
    category: str,
    title: str,
    language: str,
    framework_hint: str | None = None,
    hints: ScaffoldHints | None = None,
) -> GeneratedFile:
    """Back-compat single-scenario wrapper. Produces a grouped file
    with a single stub. Callers that group themselves should prefer
    ``emit_scaffold_group``.
    """
    return emit_scaffold_group(
        capability=capability,
        category=category,
        scenarios=[ScenarioStub(id=scenario_id, title=title)],
        language=language,
        framework_hint=framework_hint,
        hints=hints,
    )


# ---------------------------------------------------------------------
# Shared header helpers
# ---------------------------------------------------------------------

def _ts_header(capability: str, category: str) -> str:
    return (
        f"/* SCAFFOLD capability={capability} category={category} */\n"
        f"/* CONTRACT_PATH .qa-agent/state/contracts/{capability}.json */\n"
        f"/* SCENARIO_PATH .qa-agent/state/scenarios/{capability}.json */\n"
    )


def _py_header(capability: str, category: str) -> str:
    return (
        f'"""SCAFFOLD capability={capability} category={category}\n'
        f'\n'
        f'CONTRACT_PATH .qa-agent/state/contracts/{capability}.json\n'
        f'SCENARIO_PATH .qa-agent/state/scenarios/{capability}.json\n'
        f'"""\n'
    )


def _ts_fixture_block(hints: ScaffoldHints) -> tuple[str, str, str]:
    imp = (hints.fixture_import + "\n") if hints.fixture_import else ""
    setup = f"    {hints.fixture_setup};\n" if hints.fixture_setup else ""
    teardown = f"    {hints.fixture_teardown};\n" if hints.fixture_teardown else ""
    return imp, setup, teardown


def _marker(scenario_id: str, title: str) -> str:
    safe = title.replace('"', "'")
    return f"{SCAFFOLD_MARKER} :: {scenario_id} :: {safe}"


def _todo_lines(scenarios: Iterable[ScenarioStub], indent: str = "  ") -> str:
    return "\n".join(
        f'{indent}it.todo("{_marker(s.id, s.title)}");' for s in scenarios
    )


def _playwright_blocks(scenarios: Iterable[ScenarioStub], indent: str = "  ") -> str:
    parts = []
    for s in scenarios:
        parts.append(
            f'{indent}test("{_marker(s.id, s.title)}", async ({{ page }}) => {{\n'
            f'{indent}  test.fixme(true, "stub awaiting body author");\n'
            f'{indent}}});'
        )
    return "\n".join(parts)


def _pytest_functions(
    scenarios: Iterable[ScenarioStub],
    fixture_args: str,
    extra_marks: Sequence[str] = (),
) -> str:
    mark_lines = "\n".join(f"@pytest.mark.{m}" for m in extra_marks)
    if mark_lines:
        mark_lines += "\n"
    blocks = []
    seen: set[str] = set()
    for s in scenarios:
        base = slugify(s.id).replace("-", "_")
        name = base
        suffix = 1
        while name in seen:
            suffix += 1
            name = f"{base}_{suffix}"
        seen.add(name)
        blocks.append(
            f'{mark_lines}@pytest.mark.qa_agent\n'
            f'def test_{name}({fixture_args}):\n'
            f'    pytest.skip("{_marker(s.id, s.title)}")'
        )
    return "\n\n\n".join(blocks)


# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------

def _api_jest_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/api/{capability}.spec.ts"
    fx_import, fx_setup, fx_teardown = _ts_fixture_block(hints)
    body = (
        f'{_ts_header(capability, "api")}'
        f'import request from "supertest";\n'
        f'import {{ describe, it, expect, beforeEach, afterEach }} from "@jest/globals";\n'
        f'import app from "../../../qa-agent.app";\n'
        f'{fx_import}\n'
        f'describe("{capability} — api", () => {{\n'
        f'  beforeEach(async () => {{\n{fx_setup}  }});\n'
        f'  afterEach(async () => {{\n{fx_teardown}  }});\n\n'
        f'{_todo_lines(scenarios)}\n'
        f'}});\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="jest", language="typescript")


def _api_pytest_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/api/test_{capability}.py"
    fixture_block = ""
    if hints.fixture_setup or hints.fixture_teardown:
        fixture_block = (
            "@pytest.fixture(autouse=True)\n"
            "def _qa_fixture():\n"
            f"    {hints.fixture_setup or 'pass'}\n"
            "    yield\n"
            f"    {hints.fixture_teardown or 'pass'}\n\n\n"
        )
    body = (
        f'{_py_header(capability, "api")}'
        f'import pytest\n\n'
        f'{hints.fixture_import}\n\n'
        f'{fixture_block}'
        f'{_pytest_functions(scenarios, fixture_args="api_client")}\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="pytest", language="python")


# ---------------------------------------------------------------------
# UI (Playwright)
# ---------------------------------------------------------------------

def _ui_playwright_ts_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/ui/{capability}.spec.ts"
    body = (
        f'{_ts_header(capability, "ui")}'
        f'import {{ test, expect }} from "@playwright/test";\n'
        f'{hints.fixture_import}\n\n'
        f'test.describe("{capability} — ui", () => {{\n'
        f'{_playwright_blocks(scenarios)}\n'
        f'}});\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="playwright", language="typescript")


def _ui_pytest_playwright_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/ui/test_{capability}.py"
    body = (
        f'{_py_header(capability, "ui")}'
        f'import pytest\n\n'
        f'{hints.fixture_import}\n\n'
        f'{_pytest_functions(scenarios, fixture_args="page")}\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="playwright", language="python")


# ---------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------

def _security_jest_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/security/{capability}.spec.ts"
    fx_import, fx_setup, fx_teardown = _ts_fixture_block(hints)
    body = (
        f'{_ts_header(capability, "security")}'
        f'import request from "supertest";\n'
        f'import {{ describe, it, expect, beforeEach, afterEach }} from "@jest/globals";\n'
        f'import app from "../../../qa-agent.app";\n'
        f'{fx_import}\n'
        f'describe("{capability} — security", () => {{\n'
        f'  beforeEach(async () => {{\n{fx_setup}  }});\n'
        f'  afterEach(async () => {{\n{fx_teardown}  }});\n\n'
        f'{_todo_lines(scenarios)}\n'
        f'}});\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="jest", language="typescript")


def _security_pytest_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/security/test_{capability}.py"
    body = (
        f'{_py_header(capability, "security")}'
        f'import pytest\n\n'
        f'{hints.fixture_import}\n\n'
        f'{_pytest_functions(scenarios, fixture_args="api_client", extra_marks=("security",))}\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="pytest", language="python")


# ---------------------------------------------------------------------
# Accessibility (Playwright + axe)
# ---------------------------------------------------------------------

def _a11y_playwright_ts_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/accessibility/{capability}.spec.ts"
    body = (
        f'{_ts_header(capability, "accessibility")}'
        f'import {{ test, expect }} from "@playwright/test";\n'
        f'import AxeBuilder from "@axe-core/playwright";\n\n'
        f'test.describe("{capability} — accessibility", () => {{\n'
        f'{_playwright_blocks(scenarios)}\n'
        f'}});\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="playwright", language="typescript")


# ---------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------

def _perf_jest_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/performance/{capability}.spec.ts"
    body = (
        f'{_ts_header(capability, "performance")}'
        f'import request from "supertest";\n'
        f'import {{ describe, it, expect }} from "@jest/globals";\n'
        f'import app from "../../../qa-agent.app";\n\n'
        f'describe("{capability} — performance", () => {{\n'
        f'{_todo_lines(scenarios)}\n'
        f'}});\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="jest", language="typescript")


def _perf_pytest_group(capability: str, scenarios: Sequence[ScenarioStub], hints: ScaffoldHints) -> GeneratedFile:
    rel = f"tests/qa-agent/performance/test_{capability}.py"
    body = (
        f'{_py_header(capability, "performance")}'
        f'import pytest\n\n'
        f'{_pytest_functions(scenarios, fixture_args="api_client, benchmark", extra_marks=("performance",))}\n'
    )
    return GeneratedFile(rel_path=rel, body=body, framework="pytest", language="python")


# ---------------------------------------------------------------------
# Dispatch table — (category, language) → builder.
# Accessibility intentionally Playwright-only; pytest fallback rolls
# into the ui category instead.
# ---------------------------------------------------------------------

_GROUP_BUILDERS = {
    ("api", "typescript"): _api_jest_group,
    ("api", "python"): _api_pytest_group,
    ("ui", "typescript"): _ui_playwright_ts_group,
    ("ui", "python"): _ui_pytest_playwright_group,
    ("security", "typescript"): _security_jest_group,
    ("security", "python"): _security_pytest_group,
    ("accessibility", "typescript"): _a11y_playwright_ts_group,
    ("accessibility", "python"): _a11y_playwright_ts_group,
    ("performance", "typescript"): _perf_jest_group,
    ("performance", "python"): _perf_pytest_group,
}
