"""Pipeline lifecycle phases.

A single enum names every phase the controller walks through. Used by
the orchestrator to checkpoint progress and by the report to label
timeline entries.
"""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    SCAN = "scan"
    TECH_STACK = "tech_stack"
    DEPENDENCY = "dependency"
    API_SCAN = "api_scan"
    UI_SCAN = "ui_scan"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    RISK = "risk"
    STRATEGY = "strategy"
    SCENARIOS = "scenarios"
    GENERATE = "generate"
    CRITIC = "critic"
    INSTALL = "install"
    EXECUTE = "execute"
    HEAL = "heal"
    FLAKY = "flaky"
    REPORT = "report"

    @classmethod
    def ordered(cls) -> list["Phase"]:
        return list(cls)
