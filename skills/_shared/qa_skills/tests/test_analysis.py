"""analysis loader/validator tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_skills.analysis import (
    load_analysis,
    validate_analysis_dict,
    AnalysisValidationError,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_python_fastapi_ok():
    a = load_analysis(FIXTURES / "python_fastapi_analysis.json")
    assert a.language == "python"
    assert len(a.modules) == 5
    assert len(a.routes) == 10
    assert sum(1 for _ in a.api_routes()) == 7
    assert sum(1 for _ in a.page_routes()) == 3


def test_validation_rejects_missing_route_kind():
    data = json.loads((FIXTURES / "python_fastapi_analysis.json").read_text())
    del data["routes"][0]["kind"]
    errors = validate_analysis_dict(data)
    assert any("missing key: kind" in e for e in errors)


def test_validation_rejects_invalid_route_kind():
    data = json.loads((FIXTURES / "python_fastapi_analysis.json").read_text())
    data["routes"][0]["kind"] = "rpc"
    errors = validate_analysis_dict(data)
    assert any("kind not in" in e for e in errors)


def test_validation_rejects_string_frontend_files():
    """Pre-refactor analyzers emitted bare-string frontend_files. Reject."""
    data = json.loads((FIXTURES / "python_fastapi_analysis.json").read_text())
    data["frontend_files"] = ["templates/index.html"]
    errors = validate_analysis_dict(data)
    assert any("frontend_files[0] not a dict" in e for e in errors)


def test_validation_rejects_unsupported_language():
    data = json.loads((FIXTURES / "python_fastapi_analysis.json").read_text())
    data["language"] = "java"
    errors = validate_analysis_dict(data)
    assert any("language not in" in e for e in errors)


def test_strip_forbidden_keys():
    data = json.loads((FIXTURES / "python_fastapi_analysis.json").read_text())
    data["source_root"] = "/sub/package"
    data["framework"] = "fastapi"
    tmp = FIXTURES / "_tmp_strip.json"
    tmp.write_text(json.dumps(data))
    try:
        a = load_analysis(tmp, strip_forbidden=True)
        # Survives because forbidden keys were stripped before validation.
        assert a.language == "python"
    finally:
        tmp.unlink()
