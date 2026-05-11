"""Config loader: merges bundled defaults with optional project override.

Loads `<plugin>/configs/defaults.yaml`, then `<project>/.qa-agent/config.yaml`
if present, with the project file taking precedence (shallow merge by top-
level key).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError
from .paths import configs_dir, project_root


def load_config(project: str | Path | None = None) -> dict[str, Any]:
    """Return the merged config dict."""
    defaults_path = configs_dir() / "defaults.yaml"
    if not defaults_path.exists():
        raise ConfigError(f"defaults.yaml missing at {defaults_path}")
    cfg: dict[str, Any] = _load_yaml(defaults_path)

    override = project_root(project) / ".qa-agent" / "config.yaml"
    if override.exists():
        user_cfg = _load_yaml(override)
        cfg = {**cfg, **user_cfg}
    return cfg


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"config root must be a mapping: {path}")
    return data
