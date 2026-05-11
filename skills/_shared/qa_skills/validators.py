"""Schema + path validators (stdlib only).

We avoid the `jsonschema` library because it is not in stdlib and the plugin
ships without `pip install`. Instead we implement focused validators tied to
known shapes (analysis.json, AgentResult, expected_files).

Path regexes are language-aware:
  * Python projects MUST emit `test_<name>.py` files.
  * TS/JS projects MUST emit `<name>.{spec,test,api.test,...}.{ts,tsx,js,jsx}`
    files and MUST NOT use the Python `test_` prefix.

The orchestrator passes `language` ("python" | "typescript" | "javascript")
to validators; sub-agents self-validate before Write.
"""

from __future__ import annotations

import re
from pathlib import Path

# Python projects only — file MUST start with `test_` prefix, MUST end `.py`.
PY_PATH_REGEX = re.compile(
    r"^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+test_[^/]+\.py$"
)

# TS/JS projects only — file MUST end with `.spec`/`.test`/`.<cat>.test`/...
# MUST NOT start with `test_` (that is Python convention).
TS_PATH_REGEX = re.compile(
    r"^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+"
    r"(?!test_)"
    r"[^/]+\.(spec|test|api\.test|security\.test|contract\.test|a11y\.spec)\.(ts|tsx|js|jsx)$"
)

# Permissive union — used only when language is unknown (legacy callers).
ANY_PATH_REGEX = re.compile(
    r"^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+"
    r"(test_[^/]+\.py|"
    r"[^/]+\.(spec|test|api\.test|security\.test|contract\.test|a11y\.spec)\.(ts|tsx|js|jsx))$"
)

# Kept for back-compat with older imports (e.g. tests).
PATH_REGEX = ANY_PATH_REGEX

_PY_LANGS = {"python", "py"}
_TS_LANGS = {"typescript", "ts", "javascript", "js"}


def _regex_for(language: str | None) -> re.Pattern:
    if language is None:
        return ANY_PATH_REGEX
    norm = language.lower()
    if norm in _PY_LANGS:
        return PY_PATH_REGEX
    if norm in _TS_LANGS:
        return TS_PATH_REGEX
    return ANY_PATH_REGEX


def language_pattern(language: str | None) -> str:
    """Return the regex source string for path_contract.required_pattern.

    Orchestrator emits this per project so sub-agents see the right pattern.
    """
    return _regex_for(language).pattern


def validate_path(path: str, language: str | None = None) -> tuple[bool, str]:
    rx = _regex_for(language)
    if rx.match(path):
        return True, ""
    lang = (language or "any").lower()
    return False, f"path_regex_violation_{lang}:{path}"


def validate_test_output(result: dict, language: str | None = None) -> list[str]:
    """Return list of validation errors for an AgentResult dict.

    `language` enables language-aware path checks. When None, the permissive
    union pattern is used (legacy behaviour).
    """
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
                ok, err = validate_path(o["path"], language=language)
                if not ok:
                    errors.append(f"outputs[{i}].{err}")

    return errors


def validate_expected_files(expected: list[dict], language: str | None = None) -> list[str]:
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
            ok, err = validate_path(path, language=language)
            if not ok:
                errors.append(f"expected_files[{i}].{err}")
        if not covers or not isinstance(covers, list):
            errors.append(f"expected_files[{i}].covers_empty_or_not_array")
        else:
            for j, c in enumerate(covers):
                if not isinstance(c, str) or not c:
                    errors.append(f"expected_files[{i}].covers[{j}]_empty_or_not_string")
    return errors


def validate_agent_result_against_contract(
    result: dict,
    expected_files: list[dict],
    language: str | None = None,
) -> dict:
    """Diff AgentResult.outputs[] against the path_contract.expected_files[].

    Returns {extras, missing, violations}:
      * extras     — emitted paths NOT in expected_files (wrong-named files).
      * missing    — expected paths NOT emitted (sub-agent skipped them).
      * violations — emitted paths failing language-aware `validate_path`.

    The orchestrator uses this in Phase 3 post-dispatch (A2) to delete extras,
    add `missing_items[]`, and downgrade `status` to `partial` when missing>0.
    Pure function — no I/O, safe to call inside pytest.
    """
    if not isinstance(expected_files, list):
        expected_files = []
    expected: set[str] = {
        e["path"] for e in expected_files
        if isinstance(e, dict) and isinstance(e.get("path"), str)
    }
    emitted: set[str] = set()
    violations: list[str] = []

    outputs = result.get("outputs", []) if isinstance(result, dict) else []
    if isinstance(outputs, list):
        for o in outputs:
            if not isinstance(o, dict):
                continue
            p = o.get("path")
            if not isinstance(p, str) or not p:
                continue
            emitted.add(p)
            ok, err = validate_path(p, language=language)
            if not ok:
                violations.append(err)

    return {
        "extras": sorted(emitted - expected),
        "missing": sorted(expected - emitted),
        "violations": sorted(set(violations)),
    }


def assert_artifact_exists(path: str | Path, label: str) -> str | None:
    """Return error string when missing, None when present."""
    p = Path(path)
    if p.exists():
        return None
    return f"{label}_missing:{path}"


__all__ = [
    "PATH_REGEX",
    "PY_PATH_REGEX",
    "TS_PATH_REGEX",
    "ANY_PATH_REGEX",
    "language_pattern",
    "validate_path",
    "validate_test_output",
    "validate_expected_files",
    "validate_agent_result_against_contract",
    "assert_artifact_exists",
]
