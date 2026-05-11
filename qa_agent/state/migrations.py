"""State schema migrations.

Empty in v2.0.0 (no prior schema version exists yet). When a field is
added or removed, add a branch keyed on the old `schema_version` here and
bump the model's `schema_version` default.
"""

from __future__ import annotations

from typing import Any


def migrate(model_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Return `data` migrated to the current schema for `model_name`."""
    return data
