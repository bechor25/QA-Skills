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


class Scenario(BaseModel):
    id: str
    feature_id: str
    capability: str
    category: str  # api | ui | security | accessibility | performance | regression
    title: str
    description: str = ""
    steps: list[ScenarioStep] = Field(default_factory=list)
    severity: Literal["smoke", "critical", "edge", "negative"] = "smoke"


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
