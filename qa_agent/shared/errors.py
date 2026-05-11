"""Typed exceptions for qa_agent."""

from __future__ import annotations


class QAAgentError(Exception):
    """Base class for all qa_agent errors."""


class ConfigError(QAAgentError):
    """Invalid or missing configuration."""


class StateError(QAAgentError):
    """State file is missing, corrupt, or schema-incompatible."""


class ScanError(QAAgentError):
    """Scanner failed to read or interpret the project."""


class ParseError(QAAgentError):
    """AST/parser failed on a file."""


class StrategyError(QAAgentError):
    """Strategy builder produced an invalid plan."""


class GenerationError(QAAgentError):
    """Test generator produced invalid output."""


class ExecutionError(QAAgentError):
    """Subprocess executor failed."""


class InstallError(QAAgentError):
    """Dependency installation failed."""


class ReportError(QAAgentError):
    """Report builder/renderer failed."""
