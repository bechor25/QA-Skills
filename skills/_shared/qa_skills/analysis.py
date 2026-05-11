"""Load + validate analysis.json without depending on jsonschema."""

from __future__ import annotations

import json
from pathlib import Path

from .types import Analysis, LANGUAGE, ROUTE_KIND, ROUTE_PRODUCES

REQUIRED_TOP_KEYS = (
    "language", "scanned_at", "project_root", "modules", "routes", "stats",
)
REQUIRED_ROUTE_KEYS = (
    "method", "path", "handler", "file", "kind", "produces",
)
REQUIRED_MODULE_KEYS = ("path", "hash", "type")

FORBIDDEN_TOP_KEYS = (
    "source_root", "framework", "python_async_detected", "effective_project_root",
)


class AnalysisValidationError(ValueError):
    pass


def _validate_dict(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors: list[str] = []

    for k in REQUIRED_TOP_KEYS:
        if k not in data:
            errors.append(f"missing top-level key: {k}")

    if data.get("language") not in LANGUAGE:
        errors.append(f"language not in {LANGUAGE}: {data.get('language')!r}")

    forbidden_present = [k for k in FORBIDDEN_TOP_KEYS if k in data]
    if forbidden_present:
        errors.append(f"forbidden top-level keys present: {forbidden_present}")

    if not isinstance(data.get("modules"), list):
        errors.append("modules must be an array")
    else:
        for i, m in enumerate(data["modules"]):
            if not isinstance(m, dict):
                errors.append(f"modules[{i}] not a dict")
                continue
            for k in REQUIRED_MODULE_KEYS:
                if k not in m:
                    errors.append(f"modules[{i}] missing key: {k}")

    if not isinstance(data.get("routes"), list):
        errors.append("routes must be an array")
    else:
        for i, r in enumerate(data["routes"]):
            if not isinstance(r, dict):
                errors.append(f"routes[{i}] not a dict")
                continue
            for k in REQUIRED_ROUTE_KEYS:
                if k not in r:
                    errors.append(f"routes[{i}] missing key: {k}")
            if r.get("kind") not in ROUTE_KIND:
                errors.append(f"routes[{i}].kind not in {ROUTE_KIND}: {r.get('kind')!r}")
            if r.get("produces") not in ROUTE_PRODUCES:
                errors.append(f"routes[{i}].produces not in {ROUTE_PRODUCES}: {r.get('produces')!r}")

    fe = data.get("frontend_files") or []
    if not isinstance(fe, list):
        errors.append("frontend_files must be an array")
    else:
        for i, f in enumerate(fe):
            if not isinstance(f, dict):
                errors.append(f"frontend_files[{i}] not a dict (must be object since v1)")
            elif "path" not in f or "hash" not in f or "kind" not in f:
                errors.append(f"frontend_files[{i}] missing required path/hash/kind")

    return errors


def load_analysis(path: str | Path, *, strip_forbidden: bool = True) -> Analysis:
    """Load analysis.json, validate, return Analysis dataclass.

    `strip_forbidden=True` deletes keys not in spec before validation, mimicking
    the orchestrator's Phase 1a. Set False if you want to detect drift at the
    test boundary.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if strip_forbidden:
        for k in FORBIDDEN_TOP_KEYS:
            data.pop(k, None)
        if isinstance(data.get("stats"), dict):
            for k in ("framework", "language", "total_routes"):
                data["stats"].pop(k, None)

    errors = _validate_dict(data)
    if errors:
        raise AnalysisValidationError("; ".join(errors))
    return Analysis.from_dict(data)


def validate_analysis_dict(data: dict) -> list[str]:
    return _validate_dict(data)


__all__ = [
    "load_analysis",
    "validate_analysis_dict",
    "AnalysisValidationError",
    "REQUIRED_TOP_KEYS",
    "REQUIRED_ROUTE_KEYS",
    "REQUIRED_MODULE_KEYS",
    "FORBIDDEN_TOP_KEYS",
]


# CLI entry point: python -m qa_skills.analysis --analysis <path>
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="qa_skills.analysis")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--strict", action="store_true", help="Do NOT strip forbidden keys before validation")
    args = parser.parse_args()

    try:
        a = load_analysis(args.analysis, strip_forbidden=not args.strict)
    except AnalysisValidationError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(2)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)

    print(json.dumps({
        "language": a.language,
        "modules": len(a.modules),
        "routes": len(a.routes),
        "api_routes": sum(1 for _ in a.api_routes()),
        "page_routes": sum(1 for _ in a.page_routes()),
        "frontend_files": len(a.frontend_files),
        "frontend_kind": a.frontend_kind,
    }))
