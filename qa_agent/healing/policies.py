"""Self-healing policy.

What mutations are allowed per failure category? Keeping this explicit
is non-negotiable — we never want the engine quietly weakening tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .classifiers import FailureCategory

FixAction = Literal[
    "increase-timeout",
    "add-wait",
    "install-missing-dep",
    "fix-import-path",
    "no-op",
    "manual",
]


@dataclass(slots=True)
class Policy:
    max_retries: int = 2
    allowed_actions: dict[FailureCategory, list[FixAction]] = field(
        default_factory=lambda: {
            "timeout":            ["increase-timeout", "add-wait"],
            "selector":           ["add-wait", "manual"],
            "missing-dependency": ["install-missing-dep"],
            "import-path":        ["fix-import-path", "manual"],
            "auth":               ["manual"],
            "assertion":          ["manual"],  # never weaken assertions automatically
            "syntax":             ["manual"],
            "unknown":            ["manual"],
        }
    )


DEFAULT_POLICY = Policy()


def pick_action(category: FailureCategory, policy: Policy = DEFAULT_POLICY) -> FixAction:
    """Return the first allowed action for this category, or 'manual'."""
    options = policy.allowed_actions.get(category, ["manual"])
    return options[0] if options else "manual"
