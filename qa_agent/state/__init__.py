"""State management for qa_agent.

Every phase reads and writes from JSON files under
`<project>/.qa-agent/state/`. Models in `schemas` are pydantic and are the
contract between phases — code that mutates state goes through the manager.
"""

from .manager import StateManager  # noqa: F401
from .schemas import (  # noqa: F401
    DependencyGraph,
    ExecutionHistory,
    FlakyState,
    InstallationHistory,
    KnowledgeGraph,
    ProjectMap,
    RiskMatrix,
    Strategy,
)
