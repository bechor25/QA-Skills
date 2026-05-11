"""Schema + path validators (stdlib only).

We avoid the `jsonschema` library because it is not in stdlib and the plugin
ships without `pip install`. Instead we implement focused validators tied to
known shapes (analysis.json, AgentResult, expected_files).
"""

from __future__ import annotations

import re
from pathlib import Path

# Enforced by orchestrator path_contract.required_pattern. See REFACTOR_PLAN Phase 1.
PATH_REGEX = re.compile(
    r"^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+"
    r"(test_[^/]+\.py|[^/]+\.(spec|test|api\.test|security\.test|contract\.test|a11y\.spec)\.(ts|js))$"
)


def validate_path(path: str) -> tuple[bool, str]:
    if PATH_REGEX.match(path):
        return True, ""
    return False, f"path_regex_violation:{path}"


def validate_test_output(result: dict) -> list[str]:
    """Return list of validation errors for an AgentResult dict."""
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["agent_result_not_dict"]

    for k in ("agent", "status"):
        if k not in result:
            errors.append(f"missing_field:{k}")

    status = result.get("status", "")
    if not isinstance(status, str) or not status:
        errors.append("status_empty_or_not_string")
    else:
        # closed enum: passed | partial | error | skipped:<reason>
        valid = (
            status in ("passed", "partial", "error")
            or status.startswith("skipped:")
            # Backwards-compat for older sub-agents during transition (will be
            # removed in Phase 4):
            or status.startswith("skipped_")
            or status == "completed"
        )
        if not valid:
            errors.append(f"status_not_in_enum:{status}")

    outputs = result.get("outputs", [])
    if not isinstance(outputs, list):
        errors.append("outputs_not_array")
    else:
        for i, o in enumerate(outputs):
            if not isinstance(o, dict):
                errors.append(f"outputs[{i}]_not_dict")
                continue
            if "path" not in o:
                errors.append(f"outputs[{i}].path_missing")
            else:
                ok, err = validate_path(o["path"])
                if not ok:
                    errors.append(f"outputs[{i}].{err}")

    return errors


def validate_expected_files(expected: list[dict]) -> list[str]:
    errors: list[str] = []
    if not isinstance(expected, list):
        return ["expected_files_not_array"]
    for i, e in enumerate(expected):
        if not isinstance(e, dict):
            errors.append(f"expected_files[{i}]_not_dict")
            continue
        path = e.get("path")
        covers = e.get("covers")
        if not path:
            errors.append(f"expected_files[{i}].path_missing")
        else:
            ok, err = validate_path(path)
            if not ok:
                errors.append(f"expected_files[{i}].{err}")
        if not covers or not isinstance(covers, list):
            errors.append(f"expected_files[{i}].covers_empty_or_not_array")
        else:
            for j, c in enumerate(covers):
                if not isinstance(c, str) or not c:
                    errors.append(f"expected_files[{i}].covers[{j}]_empty_or_not_string")
    return errors


def assert_artifact_exists(path: str | Path, label: str) -> str | None:
    """Return error string when missing, None when present."""
    p = Path(path)
    if p.exists():
        return None
    return f"{label}_missing:{path}"


__all__ = [
    "PATH_REGEX",
    "validate_path",
    "validate_test_output",
    "validate_expected_files",
    "assert_artifact_exists",
]
