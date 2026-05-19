"""StateManager — typed load/save for every state file.

Every read returns a validated pydantic model (or the default). Every write
goes through atomic JSON write. Callers never touch raw file paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..shared.errors import StateError
from ..shared.jsonio import read_json_or, write_json
from ..shared.paths import state_dir
from . import schemas

T = TypeVar("T", bound=BaseModel)


_FILES = {
    schemas.ProjectMap: "project_map.json",
    schemas.DependencyGraph: "dependency_graph.json",
    schemas.KnowledgeGraph: "knowledge_graph.json",
    schemas.RiskMatrix: "risk_matrix.json",
    schemas.Strategy: "strategy.json",
    schemas.Scenarios: "scenarios.json",
    schemas.GeneratedTests: "generated_tests.json",
    schemas.Critique: "critique.json",
    schemas.ExecutionHistory: "execution_history.json",
    schemas.InstallationHistory: "installation_history.json",
    schemas.FlakyState: "flaky_state.json",
    schemas.UISelectorMap: "ui_selectors.json",
    schemas.TestDataPlan: "test_data_plan.json",
    schemas.RetryBudgetState: "retry_budget.json",
    schemas.RawCapabilityMap: "raw_capability_map.json",
    schemas.CapabilityMap: "capability_map.json",
    schemas.HealFailures: "heal_failures.json",
    schemas.HealClusters: "heal_clusters.json",
    schemas.HealJournal: "heal_journal.json",
    schemas.HealLedger: "heal_ledger.json",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StateManager:
    """Per-project state manager. Holds the state directory and provides
    typed accessors. All loads default to an empty model with current
    timestamps so the first run does not need to special-case missing
    files.
    """

    def __init__(self, project: str | Path | None = None) -> None:
        self.project = project
        self.dir: Path = state_dir(project)

    # ---- generic ----

    def path_for(self, model: type[BaseModel]) -> Path:
        try:
            name = _FILES[model]
        except KeyError as e:
            raise StateError(f"no registered file for model {model.__name__}") from e
        return self.dir / name

    def load(self, model: type[T], default_factory=None) -> T:
        """Load a state model, returning a default if the file is absent."""
        path = self.path_for(model)
        raw = read_json_or(path, None)
        if raw is None:
            if default_factory is not None:
                return default_factory()
            return self._empty(model)
        try:
            return model.model_validate(raw)
        except ValidationError as e:
            raise StateError(f"state file invalid: {path}: {e}") from e

    def save(self, instance: BaseModel) -> Path:
        """Atomically write a state model. Returns the path written."""
        path = self.path_for(type(instance))
        write_json(path, instance.model_dump(mode="json"))
        return path

    # ---- typed convenience accessors ----

    def project_map(self) -> schemas.ProjectMap:
        return self.load(schemas.ProjectMap)

    def dependency_graph(self) -> schemas.DependencyGraph:
        return self.load(schemas.DependencyGraph)

    def knowledge_graph(self) -> schemas.KnowledgeGraph:
        return self.load(schemas.KnowledgeGraph)

    def risk_matrix(self) -> schemas.RiskMatrix:
        return self.load(schemas.RiskMatrix)

    def strategy(self) -> schemas.Strategy:
        return self.load(schemas.Strategy)

    def execution_history(self) -> schemas.ExecutionHistory:
        return self.load(schemas.ExecutionHistory)

    def installation_history(self) -> schemas.InstallationHistory:
        return self.load(schemas.InstallationHistory)

    def flaky_state(self) -> schemas.FlakyState:
        return self.load(schemas.FlakyState)

    def heal_failures(self) -> schemas.HealFailures:
        return self.load(schemas.HealFailures)

    def heal_clusters(self) -> schemas.HealClusters:
        return self.load(schemas.HealClusters)

    def heal_journal(self) -> schemas.HealJournal:
        return self.load(schemas.HealJournal)

    def heal_ledger(self) -> schemas.HealLedger:
        return self.load(schemas.HealLedger)

    # ---- defaults ----

    def _empty(self, model: type[T]) -> T:
        now = _utcnow()
        if model is schemas.ProjectMap:
            return model(project_root=str(self.dir.parent.parent), scanned_at=now)  # type: ignore[return-value]
        if model is schemas.DependencyGraph:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.KnowledgeGraph:
            return model(built_at=now, project_summary="")  # type: ignore[return-value]
        if model is schemas.RiskMatrix:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.Strategy:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.ExecutionHistory:
            return model()  # type: ignore[return-value]
        if model is schemas.InstallationHistory:
            return model()  # type: ignore[return-value]
        if model is schemas.FlakyState:
            return model()  # type: ignore[return-value]
        if model is schemas.Scenarios:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.GeneratedTests:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.Critique:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.UISelectorMap:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.TestDataPlan:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.RetryBudgetState:
            return model()  # type: ignore[return-value]
        if model is schemas.RawCapabilityMap:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.CapabilityMap:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.HealFailures:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.HealClusters:
            return model(built_at=now)  # type: ignore[return-value]
        if model is schemas.HealJournal:
            return model()  # type: ignore[return-value]
        if model is schemas.HealLedger:
            return model()  # type: ignore[return-value]
        raise StateError(f"no default for model {model.__name__}")

    # ---- sharded state (per-capability / per-test) ----

    def _shard_dir(self, name: str) -> Path:
        path = self.dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def contract_path(self, capability: str) -> Path:
        return self._shard_dir("contracts") / f"{capability}.json"

    def load_contract(self, capability: str) -> schemas.Contract | None:
        path = self.contract_path(capability)
        raw = read_json_or(path, None)
        if raw is None:
            return None
        try:
            return schemas.Contract.model_validate(raw)
        except ValidationError as e:
            raise StateError(f"contract invalid: {path}: {e}") from e

    def save_contract(self, contract: schemas.Contract) -> Path:
        path = self.contract_path(contract.capability)
        write_json(path, contract.model_dump(mode="json"))
        return path

    def list_contract_capabilities(self) -> list[str]:
        d = self.dir / "contracts"
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.json"))

    def scenarios_shard_path(self, capability: str) -> Path:
        return self._shard_dir("scenarios") / f"{capability}.json"

    def load_capability_scenarios(self, capability: str) -> schemas.CapabilityScenarios | None:
        path = self.scenarios_shard_path(capability)
        raw = read_json_or(path, None)
        if raw is None:
            return None
        try:
            return schemas.CapabilityScenarios.model_validate(raw)
        except ValidationError as e:
            raise StateError(f"scenarios shard invalid: {path}: {e}") from e

    def save_capability_scenarios(self, scenarios: schemas.CapabilityScenarios) -> Path:
        path = self.scenarios_shard_path(scenarios.capability)
        write_json(path, scenarios.model_dump(mode="json"))
        return path

    def list_scenario_capabilities(self) -> list[str]:
        d = self.dir / "scenarios"
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.json"))

    def triage_path(self, test_id: str) -> Path:
        safe = test_id.replace("/", "_").replace("::", "__")
        return self._shard_dir("critique") / f"{safe}.json"

    def load_triage(self, test_id: str) -> schemas.TriageVerdict | None:
        path = self.triage_path(test_id)
        raw = read_json_or(path, None)
        if raw is None:
            return None
        try:
            return schemas.TriageVerdict.model_validate(raw)
        except ValidationError as e:
            raise StateError(f"triage verdict invalid: {path}: {e}") from e

    def save_triage(self, verdict: schemas.TriageVerdict) -> Path:
        path = self.triage_path(verdict.test_id)
        write_json(path, verdict.model_dump(mode="json"))
        return path
