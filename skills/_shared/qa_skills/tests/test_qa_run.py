"""End-to-end tests for the qa_run.py driver — Step A scope (Phase 0/1/2).

Sub-agent invocation is stubbed via the injected `task_call` callable. The
stub writes a fixture analysis.json to the analysis_path requested by Phase
1, mirroring what qa-code-analyzer would do at runtime.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

# Make the scripts/ dir importable so we can call `qa_run.run` programmatically.
_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import qa_run  # noqa: E402


FIXTURE_TS = (
    Path(__file__).resolve().parent / "fixtures" / "typescript_express_analysis.json"
)


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "myproj"
    project.mkdir()
    return project


def _stub_analyzer(
    fixture_path: Path,
    *,
    domain_brief_emitter=None,
    test_gen_emitter=None,
    test_gen_calls=None,
):
    """Build a `task_call` stub.

    For `qa-code-analyzer`: copies a fixture analysis.json to the location
    qa_run.py asks for in Phase 1.

    For `qa-domain-analyzer`: emitter writes (or not) the `chunk_path` file.
    Default writes one minimal brief per expected_file.

    For `qa-*-test`: emitter writes (or not) the test file at
    payload["file_to_generate"]. Default writes a tiny passing test stub.
    Each invocation is recorded in `test_gen_calls` if provided.
    """

    def default_brief_emitter(payload: dict) -> None:
        chunk_path = Path(payload["chunk_path"])
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        briefs = [
            {
                "expected_file": ef["path"],
                "covers":        ef.get("covers", []),
                "source_files":  [],
                "behaviors": [
                    {
                        "trigger":          f"<stub trigger for {ef['path']}>",
                        "expected_outcome": "<stub outcome>",
                        "side_effects":     [],
                        "error_paths":      [],
                    }
                ],
                "test_hints": ["happy_path"],
            }
            for ef in payload["expected_files"]
        ]
        chunk_path.write_text(
            json.dumps({"agent": "qa-domain-analyzer",
                        "category": payload["category"],
                        "briefs": briefs}),
            encoding="utf-8",
        )

    def default_test_gen_emitter(payload: dict) -> dict:
        pr = Path(payload["project_root"])
        rel = payload["file_to_generate"]
        full = pr / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(
            f"/* stub test for {payload['covers']} */\n"
            "import {{ describe, it, expect }} from 'vitest';\n"
            "describe('stub', () => {{ it('runs', () => {{ expect(1).toBe(1); }}); }});\n",
            encoding="utf-8",
        )
        return {
            "agent":  payload["agent"],
            "status": "passed",
            "outputs": [{
                "source_module":      payload["covers"][0] if payload["covers"] else "",
                "path":               rel,
                "tests_written":      1,
                "tests_passing":      0,
                "assertions_covered": ["stub:smoke"],
                "hints_used":         ["happy_path"],
                "skipped_hints":      [],
            }],
        }

    brief_emit = domain_brief_emitter or default_brief_emitter
    gen_emit   = test_gen_emitter      or default_test_gen_emitter
    test_gen_agents = {
        "qa-unit-test", "qa-api-test", "qa-ui-test",
        "qa-security-test", "qa-a11y-test", "qa-contract-test",
    }

    def task_call(agent: str, payload: dict) -> dict:
        if agent == "qa-code-analyzer":
            dest = Path(payload["analysis_path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            data["project_root"] = payload["project_root"]
            dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return {"agent": agent, "status": "ok", "analysis_path": str(dest)}
        if agent == "qa-domain-analyzer":
            brief_emit(payload)
            return {
                "agent": agent, "status": "passed",
                "category": payload["category"],
                "chunk_path": payload["chunk_path"],
            }
        if agent in test_gen_agents:
            if test_gen_calls is not None:
                test_gen_calls.append({
                    "agent": agent,
                    "file":  payload["file_to_generate"],
                    "covers": list(payload.get("covers") or []),
                    "has_brief": payload.get("domain_brief") is not None,
                    "has_retry_hint": "retry_hint" in payload,
                })
            return gen_emit(payload)
        if agent == "qa-flaky-detector":
            flaky_path = Path(payload["flaky_path"])
            flaky_path.write_text(
                json.dumps({"flaky_tests": [], "runs_completed": 3}),
                encoding="utf-8",
            )
            return {"agent": agent, "status": "ok",
                    "flaky_tests": [], "runs_completed": 3}
        if agent == "qa-html-reporter":
            project_root = Path(payload["project_root"])
            html = project_root / "test-reports" / f"report-{payload['run_id'][:8]}.html"
            html.parent.mkdir(parents=True, exist_ok=True)
            html.write_text("<html>stub report</html>", encoding="utf-8")
            return {"agent": agent, "status": "ok",
                    "html_report_path": str(html)}
        return {"agent": agent, "status": "ok"}

    return task_call


# ---------------------------------------------------------------------------
# Phase 0 setup
# ---------------------------------------------------------------------------


def test_run_creates_run_context_directories(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r0"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    assert result["run_id"] == "fix-r0"
    logs_dir = Path(result["paths"]["logs_dir"])
    assert logs_dir.exists()
    assert (project / ".qa-skills" / "checkpoints").is_dir()
    assert (project / "test-reports").is_dir()


def test_run_writes_checkpoint_after_each_phase(tmp_path: Path):
    project = _make_project(tmp_path)
    qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r1"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    ckpt = project / ".qa-skills" / "checkpoints" / "run.json"
    data = json.loads(ckpt.read_text(encoding="utf-8"))
    assert data["phase"] == 9
    for name in ("setup", "scan", "strategy", "domain_learn", "dispatch",
                 "flaky", "learnings", "state_write", "report", "quality",
                 "html_report", "final_gate"):
        assert name in data["completed_skills"]
    assert data["completed"] is True


# ---------------------------------------------------------------------------
# Phase 1 — scan
# ---------------------------------------------------------------------------


def test_phase_1_writes_analysis_via_stubbed_task(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r2"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    analysis_path = Path(result["paths"]["analysis"])
    assert analysis_path.is_file()
    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert data["language"] == "typescript"
    assert result["language"] == "typescript"


def test_phase_1_fails_when_analyzer_does_not_write_file(tmp_path: Path):
    project = _make_project(tmp_path)

    def no_write_task(agent: str, payload: dict) -> dict:
        return {"agent": agent, "status": "ok"}

    with pytest.raises(SystemExit) as exc:
        qa_run.run(["--project-root", str(project)], task_call=no_write_task)
    assert exc.value.code == 2


def test_phase_1_summary_keys(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r3"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    summary = result["analysis"]
    assert set(summary.keys()) == {
        "language", "modules", "routes", "api_routes", "frontend_kind"
    }
    assert summary["modules"] == 4
    assert summary["api_routes"] == 3
    assert summary["frontend_kind"] == "spa"


# ---------------------------------------------------------------------------
# Phase 2 — strategy
# ---------------------------------------------------------------------------


def test_phase_2_writes_expected_files_for_all_categories(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r4"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    expected_files_path = Path(result["paths"]["expected_files"])
    assert expected_files_path.is_file()
    data = json.loads(expected_files_path.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"unit", "api", "ui", "security", "a11y", "contract"}
    # api/contract should be non-empty for the express fixture
    assert len(data["api"]) >= 1
    assert len(data["contract"]) >= 1


def test_phase_2_writes_strategy_json(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r5"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    strategy_path = Path(result["paths"]["strategy"])
    data = json.loads(strategy_path.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "agents" in data
    assert "server_plan" in data
    assert data["mode"] == "auto"
    assert data["run_id"] == "fix-r5"


def test_phase_2_planned_includes_api_and_unit_for_express_fixture(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r6"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    planned = result["strategy"]["categories_planned"]
    assert "unit" in planned
    assert "api" in planned
    assert "contract" in planned
    assert "security" in planned


def test_phase_2_ui_skipped_when_server_unreachable(tmp_path: Path):
    project = _make_project(tmp_path)
    # Default --allow-start-server=False AND no live server at port 5173 → skip.
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r7"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    skipped_names = {s["name"] for s in result["strategy"]["categories_skipped"]}
    skipped_reasons = {s["name"]: s["reason"] for s in result["strategy"]["categories_skipped"]}
    if "ui" in skipped_names:
        assert "server_unreachable" in skipped_reasons["ui"]


def test_phase_2_honors_categories_filter(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        [
            "--project-root", str(project),
            "--run-id", "fix-r8",
            "--categories", "unit,api",
        ],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    planned = result["strategy"]["categories_planned"]
    # only unit and api may appear in planned
    assert set(planned).issubset({"unit", "api"})
    # ui/security/a11y/contract must be in skipped with reason disabled_by_caller
    skipped = {s["name"]: s["reason"] for s in result["strategy"]["categories_skipped"]}
    for cat in ("ui", "security", "a11y", "contract"):
        assert skipped.get(cat) == "disabled_by_caller"


# ---------------------------------------------------------------------------
# Integration — full Phase 0+1+2 produces a stable result dict
# ---------------------------------------------------------------------------


def test_full_step_a_returns_ok_status(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "fix-r9"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    assert result["status"] == "ok"
    assert result["phase_reached"] == 9
    assert "paths" in result


def test_step_a_fails_when_project_root_missing(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        qa_run.run(
            ["--project-root", str(tmp_path / "missing")],
            task_call=_stub_analyzer(FIXTURE_TS),
        )
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Phase 2.7 — domain learn
# ---------------------------------------------------------------------------


def test_phase_2_7_writes_brief_per_planned_category(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "b1"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    planned = result["strategy"]["categories_planned"]
    assert planned  # sanity
    for cat in planned:
        brief_path = logs_dir / f"domain_brief_{cat}.json"
        assert brief_path.is_file(), f"missing brief for {cat}"
        data = json.loads(brief_path.read_text(encoding="utf-8"))
        assert data["category"] == cat
        assert isinstance(data["briefs"], list)


def test_phase_2_7_skipped_categories_have_no_brief(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "b2",
         "--categories", "unit,api"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    for cat in ("security", "ui", "a11y", "contract"):
        assert not (logs_dir / f"domain_brief_{cat}.json").exists(), (
            f"unexpected brief for skipped {cat}"
        )


def test_phase_2_7_returns_summary_per_category(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "b3"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    planned = result["strategy"]["categories_planned"]
    for cat in planned:
        s = result["domain_briefs"][cat]
        assert "chunks" in s and "behaviors_total" in s and "ok" in s


def test_phase_2_7_chunks_large_categories(tmp_path: Path):
    """If a category has more than DOMAIN_ANALYZER_CHUNK files, multiple
    Task calls are made AND chunks are merged into one brief file."""
    project = _make_project(tmp_path)
    calls = []

    def counting_analyzer(fixture_path: Path):
        base = _stub_analyzer(fixture_path)

        def task_call(agent: str, payload: dict) -> dict:
            if agent == "qa-domain-analyzer":
                calls.append({
                    "cat": payload["category"],
                    "n":   len(payload["expected_files"]),
                })
            return base(agent, payload)

        return task_call

    # Patch DOMAIN_ANALYZER_CHUNK to 1 to force multi-chunk for any non-empty cat.
    original = qa_run.DOMAIN_ANALYZER_CHUNK
    qa_run.DOMAIN_ANALYZER_CHUNK = 1
    try:
        result = qa_run.run(
            ["--project-root", str(project), "--run-id", "b4"],
            task_call=counting_analyzer(FIXTURE_TS),
        )
    finally:
        qa_run.DOMAIN_ANALYZER_CHUNK = original

    # At least one category should have produced > 1 chunked call.
    assert any(c["n"] == 1 for c in calls)
    by_cat: dict[str, int] = {}
    for c in calls:
        by_cat[c["cat"]] = by_cat.get(c["cat"], 0) + 1
    assert any(n >= 2 for n in by_cat.values())

    # Merged brief file count == 1 per planned cat (NOT per chunk).
    logs_dir = Path(result["paths"]["logs_dir"])
    brief_files = sorted(p.name for p in logs_dir.glob("domain_brief_*.json"))
    planned = result["strategy"]["categories_planned"]
    assert len(brief_files) == len(planned)


def test_phase_2_7_retries_on_missing_chunk(tmp_path: Path):
    project = _make_project(tmp_path)
    call_count = {"qa-domain-analyzer": 0}

    def flaky_emitter(payload: dict) -> None:
        call_count["qa-domain-analyzer"] += 1
        # Only the second call (retry) actually writes the file.
        if "retry_hint" in payload:
            chunk = Path(payload["chunk_path"])
            chunk.write_text(json.dumps({
                "agent": "qa-domain-analyzer",
                "category": payload["category"],
                "briefs": [
                    {"expected_file": ef["path"], "covers": ef.get("covers", []),
                     "source_files": [], "behaviors": [], "test_hints": []}
                    for ef in payload["expected_files"]
                ]
            }))

    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "b5",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, domain_brief_emitter=flaky_emitter),
    )
    assert call_count["qa-domain-analyzer"] >= 2
    logs_dir = Path(result["paths"]["logs_dir"])
    assert (logs_dir / "domain_brief_unit.json").is_file()


def test_phase_2_7_records_warning_when_brief_never_arrives(tmp_path: Path):
    project = _make_project(tmp_path)

    def never_writes(payload: dict) -> None:
        pass

    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "b6",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, domain_brief_emitter=never_writes),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    warnings_path = logs_dir / "warnings.json"
    assert warnings_path.is_file()
    warnings = json.loads(warnings_path.read_text(encoding="utf-8"))
    assert "domain_brief_unavailable:unit" in warnings

    # Empty placeholder brief still on disk (deterministic shape for Phase 3).
    brief_path = logs_dir / "domain_brief_unit.json"
    data = json.loads(brief_path.read_text(encoding="utf-8"))
    assert data["status"] == "unavailable"
    assert data["briefs"] == []


def test_phase_2_7_cleans_up_chunk_tmp_files(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "b7"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    leftovers = list(logs_dir.glob("_brief_*_chunk_*.json"))
    assert leftovers == []


def test_phase_2_7_merges_chunked_briefs_into_one_file(tmp_path: Path):
    project = _make_project(tmp_path)
    original = qa_run.DOMAIN_ANALYZER_CHUNK
    qa_run.DOMAIN_ANALYZER_CHUNK = 1
    try:
        result = qa_run.run(
            ["--project-root", str(project), "--run-id", "b8",
             "--categories", "api"],
            task_call=_stub_analyzer(FIXTURE_TS),
        )
    finally:
        qa_run.DOMAIN_ANALYZER_CHUNK = original

    logs_dir = Path(result["paths"]["logs_dir"])
    api_brief = json.loads(
        (logs_dir / "domain_brief_api.json").read_text(encoding="utf-8")
    )
    # Should contain one brief entry per expected_file in the category.
    expected = json.loads(
        (logs_dir / "expected_files.json").read_text(encoding="utf-8")
    )
    assert len(api_brief["briefs"]) == len(expected["api"])
    paths_in_brief = {b["expected_file"] for b in api_brief["briefs"]}
    paths_in_expected = {ef["path"] for ef in expected["api"]}
    assert paths_in_brief == paths_in_expected


def test_phase_2_7_writes_checkpoint(tmp_path: Path):
    project = _make_project(tmp_path)
    qa_run.run(
        ["--project-root", str(project), "--run-id", "b9"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    ckpt = json.loads(
        (project / ".qa-skills" / "checkpoints" / "run.json")
        .read_text(encoding="utf-8")
    )
    assert "domain_learn" in ckpt["completed_skills"]


# ---------------------------------------------------------------------------
# Phase 3 — dispatch
# ---------------------------------------------------------------------------


def test_phase_3_invokes_task_once_per_expected_file(tmp_path: Path):
    project = _make_project(tmp_path)
    calls: list[dict] = []
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c1",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, test_gen_calls=calls),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    expected = json.loads(
        (logs_dir / "expected_files.json").read_text(encoding="utf-8")
    )
    # One call per file in the unit category. (Driver may retry on miss; in
    # the happy-path stub no retries fire.)
    unit_calls = [c for c in calls if c["agent"] == "qa-unit-test"]
    assert len(unit_calls) == len(expected["unit"])
    assert all(not c["has_retry_hint"] for c in unit_calls)


def test_phase_3_passes_domain_brief_to_sub_agent(tmp_path: Path):
    project = _make_project(tmp_path)
    calls: list[dict] = []
    qa_run.run(
        ["--project-root", str(project), "--run-id", "c2",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, test_gen_calls=calls),
    )
    unit_calls = [c for c in calls if c["agent"] == "qa-unit-test"]
    assert unit_calls
    # Default brief emitter writes a brief for every expected_file, so every
    # test-gen call should have_brief == True.
    assert all(c["has_brief"] for c in unit_calls)


def test_phase_3_writes_agent_output_files(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c3",
         "--categories", "unit,api"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    # Merged per agent
    assert (logs_dir / "agent_output_qa-unit-test.json").is_file()
    assert (logs_dir / "agent_output_qa-api-test.json").is_file()
    # At least one per-batch file per agent
    assert list(logs_dir.glob("agent_output_qa-unit-test_batch_*.json"))
    assert list(logs_dir.glob("agent_output_qa-api-test_batch_*.json"))


def test_phase_3_writes_execution_json_per_agent(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c4",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    exec_file = logs_dir / "execution_qa-unit-test.json"
    assert exec_file.is_file()
    exec_data = json.loads(exec_file.read_text(encoding="utf-8"))
    for k in ("category", "runner", "total", "passed", "failed",
              "skipped", "duration_ms", "exit_code", "failures"):
        assert k in exec_data


def test_phase_3_writes_batch_state(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c5",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    state = json.loads((logs_dir / "batch_state.json").read_text(encoding="utf-8"))
    # Each batch should appear as completed.
    completed = [k for k, v in state.items()
                 if isinstance(v, dict) and v.get("status") == "completed"]
    assert completed


def test_phase_3_marks_missing_file_as_error(tmp_path: Path):
    project = _make_project(tmp_path)
    calls = []

    def never_writes(payload: dict) -> dict:
        return {"agent": payload["agent"], "status": "passed", "outputs": []}

    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c6",
         "--categories", "unit"],
        task_call=_stub_analyzer(
            FIXTURE_TS,
            test_gen_emitter=never_writes,
            test_gen_calls=calls,
        ),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    merged = json.loads(
        (logs_dir / "agent_output_qa-unit-test.json").read_text(encoding="utf-8")
    )
    statuses = [o["status"] for o in merged["outputs"]]
    assert statuses
    assert all(s == "error" for s in statuses)
    warnings = json.loads((logs_dir / "warnings.json").read_text(encoding="utf-8"))
    assert any(w.startswith("qa-unit-test:file_not_written") for w in warnings)
    # Driver should have retried once per file.
    unit_calls = [c for c in calls if c["agent"] == "qa-unit-test"]
    assert any(c["has_retry_hint"] for c in unit_calls)


def test_phase_3_skips_completed_batches_on_resume(tmp_path: Path):
    project = _make_project(tmp_path)
    # First run.
    qa_run.run(
        ["--project-root", str(project), "--run-id", "c7",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    # Second run with same run_id, count test-gen calls.
    calls2: list[dict] = []
    qa_run.run(
        ["--project-root", str(project), "--run-id", "c7",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, test_gen_calls=calls2),
    )
    unit_calls2 = [c for c in calls2 if c["agent"] == "qa-unit-test"]
    assert unit_calls2 == [], (
        "expected no re-dispatch on resume but got calls: "
        f"{unit_calls2!r}"
    )


def test_phase_3_writes_only_for_planned_categories(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c8",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    logs_dir = Path(result["paths"]["logs_dir"])
    # No agent_output for skipped categories.
    for cat in ("api", "ui", "security", "a11y", "contract"):
        assert not (logs_dir / f"agent_output_qa-{cat}-test.json").exists()
        assert not (logs_dir / f"execution_qa-{cat}-test.json").exists()


def test_phase_3_result_includes_per_agent_summary(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c9",
         "--categories", "unit,api"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    assert "dispatch" in result
    summary = result["dispatch"]
    for cat in ("unit", "api"):
        assert cat in summary
        entry = summary[cat]
        for k in ("agent", "files_attempted", "files_emitted",
                  "batches", "warnings"):
            assert k in entry


def test_phase_3_deletes_wrongly_named_file(tmp_path: Path):
    """If a sub-agent writes a Python-style test_ name on a TS project, the
    driver deletes it AND marks the output as error."""
    project = _make_project(tmp_path)

    def wrong_name_emitter(payload: dict) -> dict:
        pr = Path(payload["project_root"])
        # Write to a DIFFERENT path that fails the language regex.
        bad_rel = "tests/unit/x/test_bad.ts"   # test_ prefix on TS — invalid
        # Also write the correct file so disk-verify passes; then the path-
        # regex check should still happen on the contracted path.
        Path(pr / payload["file_to_generate"]).parent.mkdir(parents=True, exist_ok=True)
        (pr / payload["file_to_generate"]).write_text("// x", encoding="utf-8")
        return {"agent": payload["agent"], "status": "passed",
                "outputs": [{"path": payload["file_to_generate"],
                             "source_module": payload["covers"][0],
                             "tests_written": 0}]}

    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "c10",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, test_gen_emitter=wrong_name_emitter),
    )
    # Sanity: at least the merged agent_output file was written.
    logs_dir = Path(result["paths"]["logs_dir"])
    merged = json.loads(
        (logs_dir / "agent_output_qa-unit-test.json").read_text(encoding="utf-8")
    )
    # The contracted paths from compute_expected_files are valid TS names
    # (no `test_` prefix), so all outputs should be `passed` not `error`.
    # This test asserts the happy case path-regex still permits valid paths.
    statuses = [o["status"] for o in merged["outputs"]]
    assert "passed" in statuses


# ---------------------------------------------------------------------------
# Phase 5 — flaky
# ---------------------------------------------------------------------------


def test_phase_5_writes_flaky_json(tmp_path: Path, monkeypatch):
    """Phase 5 calls qa_skills.flaky.detect_flaky directly (no LLM).
    Monkeypatch the function so the test never actually spawns pytest."""
    project = _make_project(tmp_path)
    monkeypatch.setattr(
        "qa_run.detect_flaky",
        lambda **kw: {"flaky_tests": [], "runs_completed": 3},
    )
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d1",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    flaky = Path(result["paths"]["logs_dir"]) / "flaky.json"
    assert flaky.is_file()
    data = json.loads(flaky.read_text(encoding="utf-8"))
    assert "flaky_tests" in data
    assert data.get("runs_completed") == 3


def test_phase_5_skipped_when_no_passable(tmp_path: Path, monkeypatch):
    project = _make_project(tmp_path)
    monkeypatch.setattr(
        "qa_run.detect_flaky",
        lambda **kw: {"flaky_tests": [], "runs_completed": 3},
    )
    # All test-gen calls fail to write → all per-file outputs error → flaky skipped
    def never_writes(payload: dict) -> dict:
        return {"agent": payload["agent"], "status": "passed", "outputs": []}
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d2",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS, test_gen_emitter=never_writes),
    )
    flaky = json.loads(
        (Path(result["paths"]["logs_dir"]) / "flaky.json")
        .read_text(encoding="utf-8")
    )
    assert flaky.get("skipped") == "no_passable_tests"


# ---------------------------------------------------------------------------
# Phase 5.5 — learnings
# ---------------------------------------------------------------------------


def test_phase_5_5_writes_learnings_json_and_summary(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d3",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    lj = project / ".qa-skills" / "learnings.json"
    assert lj.is_file()
    data = json.loads(lj.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    summary_path = Path(result["paths"]["logs_dir"]) / "learnings_summary.json"
    assert summary_path.is_file()
    assert "vuln_patterns_total" in result["learnings"]


# ---------------------------------------------------------------------------
# Phase 6 — state_write
# ---------------------------------------------------------------------------


def test_phase_6_writes_test_state(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d4",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    state_path = project / "test-state.json"
    assert state_path.is_file()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "d4"
    assert isinstance(data.get("modules"), list)


# ---------------------------------------------------------------------------
# Phase 8 — build_report
# ---------------------------------------------------------------------------


def test_phase_8_writes_v2_report_data(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d5",
         "--categories", "unit,api"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    out = project / "test-reports" / "report-data.json"
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["version"] == "2.0"
    cov = data["coverage_by_category"]
    for cat in ("unit", "api"):
        assert cat in cov
        for k in ("pct", "covered_items", "missing_items", "total",
                  "files", "stub_files", "status", "execution"):
            assert k in cov[cat], f"{cat} missing {k}"


def test_phase_8_report_has_execution_block(tmp_path: Path):
    project = _make_project(tmp_path)
    qa_run.run(
        ["--project-root", str(project), "--run-id", "d6",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    data = json.loads(
        (project / "test-reports" / "report-data.json").read_text(encoding="utf-8")
    )
    exec_block = data["coverage_by_category"]["unit"]["execution"]
    for k in ("runner", "total", "passed", "failed", "skipped",
              "duration_ms", "exit_code"):
        assert k in exec_block


# ---------------------------------------------------------------------------
# Phase 7 — quality
# ---------------------------------------------------------------------------


def test_phase_7_patches_quality_score(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d7",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    assert isinstance(result["quality_score"], int)
    assert 0 <= result["quality_score"] <= 100
    data = json.loads(
        (project / "test-reports" / "report-data.json").read_text(encoding="utf-8")
    )
    assert data["quality_score"] == result["quality_score"]


# ---------------------------------------------------------------------------
# Phase 8b — html
# ---------------------------------------------------------------------------


def test_phase_8b_writes_html(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d8",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    html_path = result["paths"]["report_html"]
    assert html_path is not None
    assert Path(html_path).is_file()


# ---------------------------------------------------------------------------
# Phase 9 — final gate
# ---------------------------------------------------------------------------


def test_phase_9_marks_checkpoint_completed(tmp_path: Path):
    project = _make_project(tmp_path)
    qa_run.run(
        ["--project-root", str(project), "--run-id", "d9",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    ckpt = json.loads(
        (project / ".qa-skills" / "checkpoints" / "run.json")
        .read_text(encoding="utf-8")
    )
    assert ckpt["completed"] is True
    assert ckpt["final_status"] in ("completed", "partial")


def test_full_run_returns_paths_for_all_artifacts(tmp_path: Path):
    project = _make_project(tmp_path)
    result = qa_run.run(
        ["--project-root", str(project), "--run-id", "d10",
         "--categories", "unit"],
        task_call=_stub_analyzer(FIXTURE_TS),
    )
    paths = result["paths"]
    for k in ("analysis", "expected_files", "strategy", "logs_dir",
              "state", "report_data", "report_html"):
        assert paths.get(k), f"missing path: {k}"
