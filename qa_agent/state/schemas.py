"""Pydantic schemas for every state file.

Versioning: each top-level model carries `schema_version`. When a field is
added/removed, bump it and add a branch to `migrations.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# project_map.json
# ----------------------------------------------------------------------

class FileEntry(BaseModel):
    path: str
    language: str
    size_bytes: int
    is_test: bool = False


class FrameworkEntry(BaseModel):
    name: str
    language: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class ProjectMap(BaseModel):
    schema_version: int = 1
    project_root: str
    scanned_at: datetime
    languages: dict[str, int] = Field(default_factory=dict)  # lang -> file count
    files: list[FileEntry] = Field(default_factory=list)
    frameworks: list[FrameworkEntry] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    # test_runners: which runner to use per surface — derived from
    # detected deps + config files (vitest > jest, playwright for UI).
    # Keys: "api" (backend tests), "ui" (browser tests), "py" (python).
    test_runners: dict[str, str] = Field(default_factory=dict)
    # dev_servers: detected dev-time ports/hostnames, used to wire
    # generated harness configs (e.g. playwright baseURL). Keys: "ui",
    # "api". Values: full URL like "http://localhost:5173".
    dev_servers: dict[str, str] = Field(default_factory=dict)


# ----------------------------------------------------------------------
# dependency_graph.json
# ----------------------------------------------------------------------

class ModuleNode(BaseModel):
    id: str
    path: str
    language: str
    imports: list[str] = Field(default_factory=list)
    imported_by: list[str] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    schema_version: int = 1
    built_at: datetime
    modules: list[ModuleNode] = Field(default_factory=list)


# ----------------------------------------------------------------------
# knowledge_graph.json
# ----------------------------------------------------------------------

class SymbolEntry(BaseModel):
    name: str
    kind: Literal["function", "class", "method", "route", "component"]
    path: str
    line: int | None = None


class FeatureEntry(BaseModel):
    id: str
    name: str
    summary: str
    module_ids: list[str] = Field(default_factory=list)
    symbols: list[SymbolEntry] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class ModuleSummary(BaseModel):
    id: str
    path: str
    summary: str
    features: list[str] = Field(default_factory=list)


class KnowledgeGraph(BaseModel):
    schema_version: int = 1
    built_at: datetime
    project_summary: str
    modules: list[ModuleSummary] = Field(default_factory=list)
    features: list[FeatureEntry] = Field(default_factory=list)


# ----------------------------------------------------------------------
# risk_matrix.json
# ----------------------------------------------------------------------

class RiskEntry(BaseModel):
    capability: str
    feature_id: str | None = None
    business_impact: int = Field(ge=0, le=5)
    state_complexity: int = Field(ge=0, le=5)
    security_exposure: int = Field(ge=0, le=5)
    change_frequency: int = Field(ge=0, le=5)
    score: float = Field(ge=0.0)
    rationale: str


class RiskMatrix(BaseModel):
    schema_version: int = 1
    built_at: datetime
    entries: list[RiskEntry] = Field(default_factory=list)


# ----------------------------------------------------------------------
# strategy.json
# ----------------------------------------------------------------------

class StrategyEntry(BaseModel):
    capability: str
    feature_id: str | None = None
    categories: list[str] = Field(default_factory=list)  # ui|api|security|...
    priority: int = Field(ge=0, le=10)
    rationale: str


class Strategy(BaseModel):
    schema_version: int = 1
    built_at: datetime
    entries: list[StrategyEntry] = Field(default_factory=list)


# ----------------------------------------------------------------------
# scenarios.json
# ----------------------------------------------------------------------

class ScenarioStep(BaseModel):
    """A single Given/When/Then step in a scenario."""

    keyword: Literal["given", "when", "then", "and"]
    text: str


class RouteHint(BaseModel):
    """Concrete route info attached to a scenario so the generator
    can emit a request targeting the real endpoint instead of `GET /`."""

    method: str            # GET | POST | PUT | PATCH | DELETE | USE | ROUTE
    pattern: str           # e.g. /users/:id
    module_path: str = ""  # source file the route was discovered in
    framework: str = ""    # Express | FastAPI | Flask | DRF | ...


class Scenario(BaseModel):
    id: str
    feature_id: str
    capability: str
    category: str  # api | ui | security | accessibility | performance | regression
    title: str
    description: str = ""
    steps: list[ScenarioStep] = Field(default_factory=list)
    severity: Literal["smoke", "critical", "edge", "negative"] = "smoke"
    route: RouteHint | None = None


class Scenarios(BaseModel):
    schema_version: int = 1
    built_at: datetime
    entries: list[Scenario] = Field(default_factory=list)


# ----------------------------------------------------------------------
# generated_tests.json
# ----------------------------------------------------------------------

class GeneratedTest(BaseModel):
    scenario_id: str
    feature_id: str
    category: str
    path: str  # repo-relative path of the generated test file
    framework: str  # pytest | jest | playwright | ...
    language: str
    summary: str = ""


class GeneratedTests(BaseModel):
    schema_version: int = 1
    built_at: datetime
    entries: list[GeneratedTest] = Field(default_factory=list)


# ----------------------------------------------------------------------
# critique.json
# ----------------------------------------------------------------------

class CritiqueFinding(BaseModel):
    rule: str
    severity: Literal["error", "warning", "info"]
    message: str
    line: int | None = None


class CritiqueResult(BaseModel):
    test_path: str
    scenario_id: str
    score: float = Field(ge=0.0, le=10.0)
    findings: list[CritiqueFinding] = Field(default_factory=list)


class Critique(BaseModel):
    schema_version: int = 1
    built_at: datetime
    results: list[CritiqueResult] = Field(default_factory=list)


# ----------------------------------------------------------------------
# execution_history.json
# ----------------------------------------------------------------------

class ExecutionRecord(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    category: str
    test_files: list[str] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    exit_code: int | None = None


class ExecutionHistory(BaseModel):
    schema_version: int = 1
    records: list[ExecutionRecord] = Field(default_factory=list)


# ----------------------------------------------------------------------
# installation_history.json
# ----------------------------------------------------------------------

class InstallRecord(BaseModel):
    run_id: str
    timestamp: datetime
    manager: str  # npm | pnpm | pip | poetry | maven | gradle
    args: list[str]
    exit_code: int
    duration_seconds: float


class InstallationHistory(BaseModel):
    schema_version: int = 1
    records: list[InstallRecord] = Field(default_factory=list)


# ----------------------------------------------------------------------
# flaky_state.json
# ----------------------------------------------------------------------

class FlakyEntry(BaseModel):
    test_id: str
    classification: Literal["timing", "network", "env", "race", "order"]
    runs: int
    failures: int
    last_seen: datetime
    rationale: str = ""


class FlakyState(BaseModel):
    schema_version: int = 1
    entries: list[FlakyEntry] = Field(default_factory=list)


# ----------------------------------------------------------------------
# contracts/<capability>.json  (sharded — one file per capability)
# Authored by the qa-enricher sub-agent.
# ----------------------------------------------------------------------

class ContractHeader(BaseModel):
    name: str
    value: str = ""
    note: str = ""


class ContractParam(BaseModel):
    name: str
    location: Literal["query", "path", "cookie"]
    required: bool = False
    schema_: dict = Field(default_factory=dict, alias="schema")
    example: object | None = None

    class Config:
        populate_by_name = True


class ContractRequest(BaseModel):
    headers: list[ContractHeader] = Field(default_factory=list)
    body_schema: dict = Field(default_factory=dict)
    query: list[ContractParam] = Field(default_factory=list)
    path_params: list[ContractParam] = Field(default_factory=list)


class ContractResponse(BaseModel):
    status_examples: list[int] = Field(default_factory=list)
    body_schema: dict = Field(default_factory=dict)
    headers: list[ContractHeader] = Field(default_factory=list)


class ContractEndpoint(BaseModel):
    method: str
    path: str
    module_path: str = ""
    auth_required: bool = False
    request: ContractRequest = Field(default_factory=ContractRequest)
    response_2xx: ContractResponse = Field(default_factory=ContractResponse)
    response_4xx: ContractResponse = Field(default_factory=ContractResponse)
    side_effects: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)


class ContractUIEntry(BaseModel):
    route: str
    file: str = ""
    needs_auth: bool = False
    primary_actions: list[str] = Field(default_factory=list)


class Contract(BaseModel):
    schema_version: int = 1
    capability: str
    built_at: datetime
    endpoints: list[ContractEndpoint] = Field(default_factory=list)
    ui_entry_points: list[ContractUIEntry] = Field(default_factory=list)
    notes: str = ""


# ----------------------------------------------------------------------
# scenarios/<capability>.json  (sharded — one file per capability)
# Authored by the qa-scenario-author sub-agent. Richer than the legacy
# top-level scenarios.json which only carried Given/When/Then prose.
# ----------------------------------------------------------------------

class ScenarioRequest(BaseModel):
    method: str = ""
    path: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: object | None = None
    query: dict[str, str] = Field(default_factory=dict)


class ScenarioExpected(BaseModel):
    status: int | None = None
    body_shape: dict = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    side_effects: list[str] = Field(default_factory=list)


class RichScenario(BaseModel):
    id: str
    capability: str
    category: str
    severity: Literal["smoke", "negative", "security", "a11y", "perf", "edge"] = "smoke"
    title: str
    endpoint_ref: dict = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    request: ScenarioRequest = Field(default_factory=ScenarioRequest)
    expected: ScenarioExpected = Field(default_factory=ScenarioExpected)
    steps: list[ScenarioStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CapabilityScenarios(BaseModel):
    schema_version: int = 1
    capability: str
    built_at: datetime
    scenarios: list[RichScenario] = Field(default_factory=list)
    notes: str = ""


# ----------------------------------------------------------------------
# ui_selectors.json  (single file, capability-keyed)
# Produced by scanners.ui_selectors during the CLI scaffold phase.
# ----------------------------------------------------------------------

class UISelector(BaseModel):
    selector: str
    role: str = ""
    label: str = ""
    file: str = ""
    line: int | None = None
    context: str = ""


class UISelectorMap(BaseModel):
    schema_version: int = 1
    built_at: datetime
    by_capability: dict[str, list[UISelector]] = Field(default_factory=dict)


# ----------------------------------------------------------------------
# critique/<test_id>.json  (sharded — one file per failing test)
# Authored by the qa-triage sub-agent.
# ----------------------------------------------------------------------

class TriageEvidence(BaseModel):
    expected_per_contract: str = ""
    actual_request: dict = Field(default_factory=dict)
    actual_response: dict = Field(default_factory=dict)
    code_location_at_fault: str = ""


class TriageAction(BaseModel):
    type: Literal["edit_test", "report_bug", "retry_only", "halt"] = "retry_only"
    diff: str = ""
    rationale: str = ""
    summary: str = ""


class TriageVerdict(BaseModel):
    schema_version: int = 1
    test_id: str
    test_path: str = ""
    verdict: Literal["test-bug", "prod-bug", "flaky", "infra"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: TriageEvidence = Field(default_factory=TriageEvidence)
    action: TriageAction = Field(default_factory=TriageAction)
    built_at: datetime


# ----------------------------------------------------------------------
# test_data_plan.json  (single file)
# Emitted by runtime.test_data based on the detected ORM. Tells the
# scaffolder which fixture/teardown helper to import.
# ----------------------------------------------------------------------

class TestDataPlan(BaseModel):
    schema_version: int = 1
    built_at: datetime
    orm: Literal["prisma", "typeorm", "sequelize", "drizzle", "mongoose",
                 "sqlalchemy", "django-orm", "tortoise", "none"] = "none"
    strategy: Literal["transactional", "truncate", "container", "api-fixtures", "none"] = "none"
    helper_import: str = ""           # e.g. "import { useFixture } from '../helpers/fixtures'"
    setup_call: str = ""              # e.g. "await fixtures.reset()"
    teardown_call: str = ""           # e.g. "await fixtures.rollback()"
    notes: str = ""


# ----------------------------------------------------------------------
# retry_budget.json  (single file)
# Tracks per-test attempt counts and frozen verdicts so the orchestrator
# never exceeds the configured budget or retries a prod-bug.
# ----------------------------------------------------------------------

class RetryEntry(BaseModel):
    test_id: str
    attempts: int = 0
    frozen_verdict: Literal["test-bug", "prod-bug", "flaky", "infra", ""] = ""
    last_run_id: str = ""
    last_seen: datetime


class RetryBudgetState(BaseModel):
    schema_version: int = 1
    max_attempts: int = 2
    entries: list[RetryEntry] = Field(default_factory=list)


# ----------------------------------------------------------------------
# capability_map.json (CLI-built clustering of routes/pages into
# project-specific capabilities) + raw_capability_map.json (the
# pre-refinement version emitted by the deterministic clusterer).
# ----------------------------------------------------------------------

class DiscoveredCapability(BaseModel):
    name: str
    summary: str = ""
    route_globs: list[str] = Field(default_factory=list)
    ui_globs: list[str] = Field(default_factory=list)
    route_count: int = 0
    ui_count: int = 0
    sample_routes: list[str] = Field(default_factory=list)
    sample_ui_files: list[str] = Field(default_factory=list)
    score_hint: float = 0.0


class CapabilityMap(BaseModel):
    schema_version: int = 1
    built_at: datetime
    source: Literal["clusterer", "mapper-agent"] = "clusterer"
    capabilities: list[DiscoveredCapability] = Field(default_factory=list)


class RawCapabilityMap(BaseModel):
    """Same shape as CapabilityMap but emitted by the deterministic
    clusterer before the optional refinement sub-agent runs."""
    schema_version: int = 1
    built_at: datetime
    capabilities: list[DiscoveredCapability] = Field(default_factory=list)
