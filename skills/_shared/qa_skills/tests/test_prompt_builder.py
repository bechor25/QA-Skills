"""prompt_builder tests — bounded per-file sub-agent payloads."""

from __future__ import annotations

import json

import pytest

from qa_skills.prompt_builder import (
    PROMPT_SIZE_CAP_CHARS,
    PRIOR_SUMMARY_MAX_LINES,
    REFERENCE_BY_CATEGORY,
    PromptTooLarge,
    build_domain_analyzer_prompt,
    build_test_gen_prompt,
)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def _ef(path: str = "tests/unit/auth/login.test.ts",
        covers=("src/auth/login.ts",)) -> dict:
    return {"path": path, "covers": list(covers)}


def _brief(file: str, hints=("happy_path",)) -> dict:
    return {
        "expected_file": file,
        "covers":        ["src/auth/login.ts"],
        "source_files":  ["src/auth/login.ts"],
        "behaviors": [
            {"trigger": "POST /login", "expected_outcome": "200 with {token}",
             "side_effects": [], "error_paths": []}
        ],
        "test_hints": list(hints),
    }


def test_build_test_gen_prompt_has_one_file():
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=_brief("tests/unit/auth/login.test.ts"),
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
    )
    assert p["file_to_generate"] == "tests/unit/auth/login.test.ts"
    assert p["covers"] == ["src/auth/login.ts"]


def test_build_test_gen_prompt_includes_reference_for_category():
    """reference_pattern must be an absolute path under plugin root, not the
    relative `reference/<file>` literal — sub-agents have no PLUGIN_ROOT."""
    for cat, rel in REFERENCE_BY_CATEGORY.items():
        p = build_test_gen_prompt(
            agent=f"qa-{cat}-test",
            category=cat,
            expected_file=_ef(path=f"tests/{cat}/x/x.test.ts"),
            domain_brief=None,
            language="typescript",
            project_root="/abs/path",
            run_id="r1",
        )
        assert p["reference_pattern"].startswith("/"), p["reference_pattern"]
        assert p["reference_pattern"].endswith(rel), (
            f"expected suffix {rel}, got {p['reference_pattern']}"
        )


def test_build_test_gen_prompt_excludes_other_files_briefs():
    """Brief for file A must not include file B's brief entry."""
    full_brief = {
        "category": "api",
        "briefs": [
            _brief("tests/api/auth/login.api.test.ts", hints=("happy_path",)),
            _brief("tests/api/users/users.api.test.ts",
                   hints=("happy_path", "auth_missing")),
        ],
    }
    p = build_test_gen_prompt(
        agent="qa-api-test",
        category="api",
        expected_file=_ef(path="tests/api/auth/login.api.test.ts",
                          covers=("POST /api/login",)),
        domain_brief=full_brief,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
    )
    assert p["domain_brief"]["expected_file"] == "tests/api/auth/login.api.test.ts"
    # No data from the users brief should leak.
    blob = json.dumps(p)
    assert "tests/api/users/users.api.test.ts" not in blob


def test_build_test_gen_prompt_passes_through_pre_sliced_brief():
    """If caller passes a single-entry brief dict already, use it as-is."""
    brief = _brief("tests/unit/auth/login.test.ts")
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=brief,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
    )
    assert p["domain_brief"] == brief


def test_build_test_gen_prompt_handles_none_brief():
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=None,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
    )
    assert p["domain_brief"] is None


# ---------------------------------------------------------------------------
# Prior summary bounds
# ---------------------------------------------------------------------------


def test_prior_summary_capped_at_max_lines():
    long_list = [f"tests/unit/x/x{i}.test.ts" for i in range(20)]
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=None,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
        prior_summary=long_list,
    )
    assert len(p["prior_summary"]) <= PRIOR_SUMMARY_MAX_LINES


def test_prior_summary_deduplicates():
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=None,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
        prior_summary=["a", "b", "a", "c", "b"],
    )
    assert p["prior_summary"] == ["a", "b", "c"]


def test_prior_summary_empty_when_omitted():
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=None,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
    )
    assert p["prior_summary"] == []


# ---------------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------------


def test_prompt_size_under_cap_for_realistic_payload():
    brief = {
        "expected_file": "tests/api/auth/login.api.test.ts",
        "covers":        ["POST /api/login"],
        "source_files":  ["apps/api/src/routes/auth.ts"],
        "behaviors": [{
            "trigger": "POST /api/login {email, password}",
            "expected_outcome": "200 with {token, refreshToken, user}",
            "side_effects": ["RefreshToken row created", "auditLog row created"],
            "error_paths": [
                {"trigger": "missing email",   "outcome": "400 ValidationError"},
                {"trigger": "wrong password",  "outcome": "401 InvalidCredentials"},
                {"trigger": "5 failed attempts","outcome": "429 RateLimited"},
            ],
        }],
        "test_hints": [
            "happy_path", "validation_missing_field:email",
            "auth_missing", "rate_limit",
        ],
    }
    p = build_test_gen_prompt(
        agent="qa-api-test",
        category="api",
        expected_file=_ef(path="tests/api/auth/login.api.test.ts",
                          covers=("POST /api/login",)),
        domain_brief=brief,
        language="typescript",
        project_root="/abs/path",
        run_id="abc-123-def",
        prior_summary=["tests/api/users/users.api.test.ts"],
    )
    size = len(json.dumps(p))
    assert size < PROMPT_SIZE_CAP_CHARS, f"size={size}"


def test_prompt_raises_when_oversize():
    # Construct a domain_brief that pushes payload over the cap.
    fat_brief = {
        "expected_file": "tests/api/x/x.api.test.ts",
        "covers":        ["GET /api/x"],
        "source_files":  ["apps/api/src/routes/x.ts"],
        "behaviors":     [],
        "test_hints":    ["happy_path"] * 5000,  # ~50KB serialized
    }
    with pytest.raises(PromptTooLarge):
        build_test_gen_prompt(
            agent="qa-api-test",
            category="api",
            expected_file=_ef(path="tests/api/x/x.api.test.ts"),
            domain_brief=fat_brief,
            language="typescript",
            project_root="/abs/path",
            run_id="r1",
        )


# ---------------------------------------------------------------------------
# UI/a11y server_plan threading
# ---------------------------------------------------------------------------


def test_ui_prompt_includes_server_plan():
    sp = {"url": "http://localhost:5173", "start_command": None,
          "start_allowed": False, "timeout_seconds": 30, "cleanup_pid": None}
    p = build_test_gen_prompt(
        agent="qa-ui-test",
        category="ui",
        expected_file=_ef(path="tests/ui/Login/Login.spec.ts",
                          covers=("src/pages/Login.tsx",)),
        domain_brief=None,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
        server_plan=sp,
        frontend_kind="spa",
    )
    assert p["server_plan"] == sp
    assert p["frontend_kind"] == "spa"


def test_unit_prompt_does_not_include_server_plan():
    sp = {"url": "http://localhost:5173"}
    p = build_test_gen_prompt(
        agent="qa-unit-test",
        category="unit",
        expected_file=_ef(),
        domain_brief=None,
        language="typescript",
        project_root="/abs/path",
        run_id="r1",
        server_plan=sp,
        frontend_kind="spa",
    )
    assert "server_plan" not in p
    assert "frontend_kind" not in p


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_rejects_non_dict_expected_file():
    with pytest.raises(TypeError):
        build_test_gen_prompt(
            agent="qa-unit-test",
            category="unit",
            expected_file="tests/unit/x/x.test.ts",  # wrong type
            domain_brief=None,
            language="typescript",
            project_root="/abs/path",
            run_id="r1",
        )


def test_rejects_expected_file_missing_path():
    with pytest.raises(ValueError):
        build_test_gen_prompt(
            agent="qa-unit-test",
            category="unit",
            expected_file={"covers": ["x"]},
            domain_brief=None,
            language="typescript",
            project_root="/abs/path",
            run_id="r1",
        )


def test_rejects_expected_file_missing_covers():
    with pytest.raises(ValueError):
        build_test_gen_prompt(
            agent="qa-unit-test",
            category="unit",
            expected_file={"path": "tests/unit/x/x.test.ts"},
            domain_brief=None,
            language="typescript",
            project_root="/abs/path",
            run_id="r1",
        )


# ---------------------------------------------------------------------------
# build_domain_analyzer_prompt
# ---------------------------------------------------------------------------


def test_build_domain_analyzer_prompt_shape():
    p = build_domain_analyzer_prompt(
        run_id="r1",
        project_root="/abs/path",
        category="api",
        language="typescript",
        logs_dir="/abs/path/.qa-skills/logs/r1",
        chunk_path="/abs/path/.qa-skills/logs/r1/_brief_api_chunk_000.json",
        expected_files=[{"path": "tests/api/auth/login.api.test.ts",
                         "covers": ["POST /api/login"]}],
        analysis_path="/abs/path/.qa-skills/logs/r1/analysis.json",
    )
    assert p["category"] == "api"
    assert p["chunk_path"].endswith(".json")
    assert len(p["expected_files"]) == 1


def test_domain_analyzer_prompt_size_cap_enforced():
    big_files = [
        {"path": f"tests/api/m{i}/m{i}.api.test.ts",
         "covers": [f"GET /api/m{i}"]}
        for i in range(2000)
    ]
    with pytest.raises(PromptTooLarge):
        build_domain_analyzer_prompt(
            run_id="r1",
            project_root="/abs/path",
            category="api",
            language="typescript",
            logs_dir="/abs/path/.qa-skills/logs/r1",
            chunk_path="/abs/path/.qa-skills/logs/r1/_brief_api_chunk_000.json",
            expected_files=big_files,
            analysis_path="/abs/path/.qa-skills/logs/r1/analysis.json",
        )
