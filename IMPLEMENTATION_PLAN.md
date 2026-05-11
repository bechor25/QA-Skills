# QA-Skills v2 — Implementation Plan

**Source:** [ARCHITECTURE_DIAGNOSTIC.md](ARCHITECTURE_DIAGNOSTIC.md) §5–§6
**Goal:** Python-driven pipeline. LLM bounded to per-file work.
**Estimated effort:** ~2 working days
**Pytest baseline at start:** 245 green

---

## 0. Ground rules

1. **No deletion before replacement.** Each step keeps old + new running in parallel; cutover at Step E.
2. **Pytest green after every step.** No step lands red. Each step adds tests, not removes.
3. **Hebrew→English commit messages.** Plugin is English-default.
4. **One PR-per-step (logical), squash optional.** History tells the story.
5. **No fake `Task` calls.** Driver invokes Task via `subprocess` to `claude` CLI OR via injected callable (tests use callable; runtime uses CLI). Single seam.

---

## 1. File-by-file inventory (what touches what)

### 1.1 New files

| Path                                                          | LOC est | Purpose                                                                |
|---------------------------------------------------------------|---------|------------------------------------------------------------------------|
| `scripts/qa_run.py`                                           | 400     | Top-level Python driver. Phase 0→9.                                    |
| `qa_skills/driver.py`                                         | 200     | Task subprocess seam, retry-once, verify_on_disk, prior_summary cache. |
| `qa_skills/prompt_builder.py`                                 | 250     | Per-sub-agent tiny prompt JSON. Single-file scope.                     |
| `qa_skills/tests/test_driver.py`                              | 120     | Unit tests for driver helpers w/ stubbed Task.                         |
| `qa_skills/tests/test_prompt_builder.py`                      | 100     | Builder shape + size cap (≤4k tokens input).                           |
| `qa_skills/tests/test_qa_run.py`                              | 250     | End-to-end driver with stubbed Task. Asserts every artifact on disk.   |
| `CHANGELOG.md`                                                | 30      | v2.0 entry.                                                            |

### 1.2 Modified files

| Path                                              | Before | After   | Diff                                          |
|---------------------------------------------------|--------|---------|-----------------------------------------------|
| `agents/qa-orchestrator.md`                       | 880    | ~40     | Becomes wrapper around `qa_run.py`.           |
| `agents/qa-unit-test.md`                          | 262    | ~80     | One-file scope. No phases. No gates.          |
| `agents/qa-api-test.md`                           | 286    | ~80     | Same.                                         |
| `agents/qa-security-test.md`                      | 317    | ~80     | Same.                                         |
| `agents/qa-contract-test.md`                      | 198    | ~80     | Same.                                         |
| `agents/qa-ui-test.md`                            | 514    | ~120    | One-file scope. server_plan from driver.      |
| `agents/qa-a11y-test.md`                          | 281    | ~120    | Same.                                         |
| `agents/qa-domain-analyzer.md`                    | 174    | ~120    | Per-category scope, smaller batch.            |
| `skills/test-orchestrator/SKILL.md`               | ~50    | ~50     | Unchanged. Still invokes qa-orchestrator agent. |
| `README.md`                                       | ~?     | ~?      | Update architecture diagram.                  |

### 1.3 Deleted files

| Path                                  | Reason                                          |
|---------------------------------------|-------------------------------------------------|
| `agents/qa-coverage-reporter.md`      | Replaced by driver call to `build_report.py`.   |
| `RUNTIME_ENFORCEMENT_PLAN.md`         | Superseded by this plan.                        |
| `STUB_FIX_PLAN.md`                    | Superseded.                                     |

### 1.4 Untouched (already correct)

- `qa_skills/{path_planner,strategy,budget,agent_log,runner,coverage,report_builder,validators,stub_markers,server,analysis,final_gate,state,quality,html_render,learnings,gaps,artifacts,flaky,git_diff,routes}.py`
- `scripts/{plan_expected_files,strategy,validate_analysis,server_plan,state_write,quality,build_report,final_gate,run_tests,validate_test_output,contract_diff,agent_log,budget}.py`
- `reference/*.md`
- `agents/{qa-code-analyzer,qa-env-validator,qa-flaky-detector,qa-git-diff-analyzer,qa-html-reporter,qa-learnings-validator}.md` (already small + bounded)

---

## 2. Step A — Driver skeleton + Phase 1/2

**Goal:** `qa_run.py` runs Phases 0/1/2 deterministically. No LLM dispatch yet.

### 2.1 New code

**`qa_skills/driver.py`** — 200 LOC:

```python
TaskCall = Callable[[str, dict], dict]  # injected; default = subprocess

def task_subprocess(agent: str, payload: dict, timeout: int = 600) -> dict:
    # spawn `claude -p ...` (or Task CLI equivalent) with payload on stdin
    # parse JSON from stdout
    # raises TaskTimeout / TaskError on failure

def verify_on_disk(path: Path, *, must_be_json: bool = True) -> dict | None:
    # returns parsed JSON if exists+valid; None otherwise

def retry_once(fn, *, on_failure_prompt_suffix: str) -> dict:
    # generic retry shape for Task calls when verification fails

def build_run_context(project_path, locale, mode, options) -> dict:
    # mirrors Phase 0 setup deterministically

def write_checkpoint(checkpoint_dir, run_id, phase, phase_name, completed=False):
    # atomic
```

**`scripts/qa_run.py`** — Phase 0/1/2 only at this step (~150 LOC of the eventual 400):

```python
def main(argv):
    args = parse_args(argv)              # --project, --locale, --mode, --categories, --force-full
    rc = build_run_context(...)
    phase_0_setup(rc)
    phase_1_scan(rc, task_call=task_subprocess)
    phase_2_strategy(rc)
    print(json.dumps({"phase_reached": 2, "run_id": rc["run_id"]}))
```

**`qa_skills/tests/test_driver.py`** — 60 LOC for Step A:
- `test_task_subprocess_parses_stdout`
- `test_task_subprocess_handles_timeout`
- `test_verify_on_disk_returns_none_when_missing`
- `test_retry_once_succeeds_on_second_try`
- `test_write_checkpoint_atomic`

**`qa_skills/tests/test_qa_run.py`** — 80 LOC for Step A:
- `test_phase_0_creates_dirs`
- `test_phase_1_writes_analysis_json_with_stubbed_task`
- `test_phase_2_writes_strategy_and_expected_files`

### 2.2 Acceptance for Step A

- `pytest` → 245 + ~10 new = 255 green
- `python3 scripts/qa_run.py --project /tmp/empty-fixture --locale en` produces `analysis.json`, `strategy.json`, `expected_files.json` (using stubbed Task in fixture)
- No regressions in existing wrappers
- Old `qa-orchestrator.md` still works in parallel (unmodified)

### 2.3 Risks for Step A

- **`Task` CLI shape unknown.** Mitigation: implement `task_subprocess` against a single seam. Test path uses injected callable. Real CLI form discovered at Step E cutover; only one function changes.
- **`run_id` collision** between driver-run and orchestrator-run. Mitigation: driver generates uuid4; orchestrator already does same.

---

## 3. Step B — Phase 2.7 forced domain learn

**Goal:** Driver iterates planned categories and forces `domain_brief_<cat>.json` on disk.

### 3.1 New code

**`scripts/qa_run.py`** — add Phase 2.7 (~50 LOC):

```python
def phase_2_7_domain_learn(rc, task_call):
    planned = rc["plan"]["summary"]["categories_planned"]
    expected = read_json(rc["logs_dir"] / "expected_files.json")
    warnings = []

    for cat in planned:
        payload = build_domain_analyzer_input(rc, cat, expected[cat])
        result = task_call("qa-domain-analyzer", payload)

        brief_path = rc["logs_dir"] / f"domain_brief_{cat}.json"
        brief = verify_on_disk(brief_path)

        if brief is None or not brief.get("briefs"):
            # retry once with explicit suffix
            payload["retry_hint"] = "Your previous output did not produce a brief on disk. Re-run STRICTLY per qa-domain-analyzer.md Phase 5. Write to disk and emit at least one behavior per expected_file."
            result = task_call("qa-domain-analyzer", payload)
            brief = verify_on_disk(brief_path)

        if brief is None or not brief.get("briefs"):
            warnings.append(f"domain_brief_unavailable:{cat}")
            # write empty placeholder so Phase 3 has a deterministic file
            write_json(brief_path, {"category": cat, "briefs": [], "status": "unavailable"})

    write_json(rc["logs_dir"] / "warnings.json", warnings)
    write_checkpoint(rc, phase=2.7, phase_name="domain_learn")
```

**Important:** the driver caps `qa-domain-analyzer` payload to **≤ N expected_files per call**. Large categories split into chunks; merge briefs into single `domain_brief_<cat>.json`.

```python
DOMAIN_ANALYZER_CHUNK = 8  # ≤ 8 files per call → keeps input prompt bounded

def build_domain_analyzer_input(rc, cat, expected_files):
    return [
        {"category": cat, "expected_files": chunk, ...}
        for chunk in chunked(expected_files, DOMAIN_ANALYZER_CHUNK)
    ]
```

Driver loops chunks, concats `briefs[]`, writes ONE `domain_brief_<cat>.json`.

### 3.2 `agents/qa-domain-analyzer.md` shrink

Cut from 174 → ~120 lines. Drop:
- Boilerplate phase numbering
- Repeated "you MUST" prose
- Locale rules (driver handles locale)

Keep:
- Hint vocabulary (closed list)
- Behavior extraction shape
- Output JSON schema

### 3.3 Tests added

**`qa_skills/tests/test_qa_run.py`** — +60 LOC:
- `test_phase_2_7_writes_brief_per_category`
- `test_phase_2_7_retries_on_empty_brief`
- `test_phase_2_7_records_warning_when_still_empty_after_retry`
- `test_phase_2_7_chunks_large_categories`
- `test_phase_2_7_merges_chunked_briefs_into_one_file`

### 3.4 Acceptance for Step B

- pytest → ~260 green
- Driver run on Candidate_Mngmnt (with stubbed Task echoing minimal valid brief) produces `domain_brief_<cat>.json` × 6 with `briefs[]` non-empty
- Warning persisted in `warnings.json` when brief is empty after retry

---

## 4. Step C — Phase 3 file-per-Task dispatch + sub-agent MD shrink

**Goal:** Driver iterates files. Each Task call = exactly 1 expected_file. Driver runs tests itself.

### 4.1 New code

**`qa_skills/prompt_builder.py`** — 250 LOC:

```python
def build_test_gen_prompt(*, agent: str, expected_file: dict, domain_brief: dict,
                          language: str, project_root: str, run_id: str,
                          prior_summary: list[str], reference_pattern_path: str) -> dict:
    # returns dict with hard cap on size:
    #   - file_to_generate: 1 path
    #   - covers: 1-N source paths/routes
    #   - domain_brief: only this file's slice (behaviors[] + test_hints[])
    #   - language, project_root, run_id
    #   - prior_summary: ≤ 5 lines, file paths only, no code
    #   - reference: path to reference/<cat>-test-patterns.md (agent reads it)
    # asserts total JSON < 4096 chars before return

def build_domain_analyzer_prompt(...): ...
```

**`scripts/qa_run.py`** — Phase 3 dispatch (~200 LOC):

```python
def phase_3_dispatch(rc, task_call):
    state = load_batch_state(rc["logs_dir"])
    expected = read_json(rc["logs_dir"] / "expected_files.json")

    for cat in rc["plan"]["summary"]["categories_planned"]:
        agent = CATEGORY_TO_AGENT[cat]
        brief_by_path = index_brief_by_path(rc["logs_dir"] / f"domain_brief_{cat}.json")
        all_files = expected[cat]

        for batch_idx, batch in enumerate(split_into_batches(all_files, 3)):
            if is_completed(state, cat, batch_idx):
                continue

            batch_results = []
            for ef in batch:
                prompt = build_test_gen_prompt(
                    agent=agent,
                    expected_file=ef,
                    domain_brief=brief_by_path.get(ef["path"], {}),
                    language=rc["language"],
                    project_root=rc["project_root"],
                    run_id=rc["run_id"],
                    prior_summary=summarize_prior(state, cat, max_lines=5),
                    reference_pattern_path=REFERENCE_BY_CAT[cat],
                )
                result = task_call(agent, prompt)

                # ---- verification gates (driver runs them, not sub-agent) ----
                full_path = Path(rc["project_root"]) / ef["path"]
                if not full_path.exists():
                    result = retry_once(lambda: task_call(agent, prompt),
                                        on_failure_prompt_suffix="File not written. Write to exactly the path specified.")
                if not full_path.exists():
                    result["status"] = "error"
                    result["reason"] = "file_not_written"
                    batch_results.append(result)
                    continue

                lang_ok, reason = validate_path(ef["path"], rc["language"])
                if not lang_ok:
                    full_path.unlink(missing_ok=True)
                    result["status"] = "error"
                    result["reason"] = reason
                    batch_results.append(result)
                    continue

                # ---- contract diff (driver) ----
                diff = contract_diff_one(ef, result, rc["language"])
                # ---- execution (driver runs tests, NOT sub-agent) ----
                exec_result = runner.run_tests(
                    category=cat,
                    project_root=rc["project_root"],
                    language=rc["language"],
                    files=[full_path],
                )
                result["execution_result"] = exec_result
                batch_results.append(result)

            # ---- persist batch ----
            agent_log.write_agent_output(
                logs_dir=rc["logs_dir"],
                agent=agent,
                payload={"agent": agent, "status": collapse_status(batch_results),
                         "outputs": batch_results},
                batch_idx=batch_idx,
            )
            mark_completed(state, cat, batch_idx, [ef["path"] for ef in batch])
            save_batch_state(rc["logs_dir"], state)

        # collapse all batches of this cat → merged agent_output_<agent>.json
        agent_log.write_merged_agent_output(rc["logs_dir"], agent, ...)
```

### 4.2 Sub-agent MD shrink (qa-unit-test as exemplar)

New `agents/qa-unit-test.md` (~80 lines):

```markdown
---
name: qa-unit-test
description: Generate ONE unit test file for ONE source module. Driver calls you per-file with bounded scope.
model: sonnet
tools: Read, Write, Edit, Grep
---

You are invoked **once per source file** by the QA-Skills driver. You receive
a tiny JSON payload describing exactly one file to write. The driver handles
batching, execution, telemetry, and reporting — you do not.

# Input shape

```json
{
  "file_to_generate": "tests/unit/auth/login.test.ts",
  "covers": ["src/auth/login.ts"],
  "language": "typescript",
  "domain_brief": {
    "behaviors": [...],
    "test_hints": ["happy_path", "validation_missing_field:email", ...],
    "source_excerpt": "≤ 200 lines of the source file"
  },
  "reference_pattern_path": "${CLAUDE_PLUGIN_ROOT}/reference/unit-test-patterns.md",
  "project_root": "/abs/path",
  "prior_summary": ["tests/unit/auth/jwt.test.ts", ...]
}
```

# Output (return JSON only)

```json
{
  "agent": "qa-unit-test",
  "status": "passed | partial | error",
  "outputs": [
    {
      "source_module": "src/auth/login.ts",
      "path": "tests/unit/auth/login.test.ts",
      "tests_written": 8,
      "assertions_covered": ["loginUser:happy_path", ...],
      "hints_used": ["happy_path", "validation_missing_field:email"],
      "skipped_hints": []
    }
  ]
}
```

# Hard rules

1. Write **exactly one file** at `input.file_to_generate`. Never others.
2. Generate **one `it`/`test` per entry in `domain_brief.test_hints[]`**.
3. Assert against `behaviors[*].expected_outcome` — payload shape AND side effects.
4. Mock external I/O. Pure logic only.
5. Read `input.reference_pattern_path` once for language-specific templates.

# Forbidden

- `expect(true).toBe(true)` — stub marker. Returns `status: error`.
- Tests for hypothetical behavior not in `domain_brief`.
- Multi-file output.
- Phase numbering, banners, Bash gates — driver owns those.

# Mandatory header

(unchanged from existing reference)
```

Same shape applied to qa-api-test, qa-security-test, qa-contract-test, qa-ui-test, qa-a11y-test.

For ui/a11y: payload also carries `server_plan` (driver-resolved) and `frontend_files` slice for THIS file only.

### 4.3 Tests added

**`qa_skills/tests/test_prompt_builder.py`** — 100 LOC:
- `test_prompt_includes_only_one_file`
- `test_prompt_includes_domain_brief_slice_for_that_file`
- `test_prompt_excludes_other_files_briefs`
- `test_prompt_size_under_cap_4096_chars`
- `test_prompt_includes_reference_path`
- `test_prompt_prior_summary_capped_at_5_lines`

**`qa_skills/tests/test_qa_run.py`** — +110 LOC:
- `test_phase_3_one_task_call_per_file`
- `test_phase_3_writes_agent_output_after_each_batch`
- `test_phase_3_writes_execution_json_per_category`
- `test_phase_3_skips_completed_batches_on_resume`
- `test_phase_3_deletes_file_with_wrong_name`
- `test_phase_3_marks_missing_file_as_error`
- `test_phase_3_runs_tests_via_runner_module`

### 4.4 Acceptance for Step C

- pytest → ~285 green
- Driver run produces:
  - `agent_output_<agent>.json` × 6 (merged)
  - `agent_output_<agent>_batch_<NNN>.json` × many (per-batch)
  - `execution_<agent>.json` × 6 (real runner output)
  - `batch_state.json` with all batches marked completed
- Each sub-agent prompt JSON < 4096 chars (asserted by builder)

---

## 5. Step D — Phases 5/6/7/8/9 = pure Python

**Goal:** Driver finishes the pipeline without any LLM coverage-reporter.

### 5.1 Driver code additions

**`scripts/qa_run.py`** — final ~100 LOC:

```python
def phase_5_flaky(rc, task_call):
    # subprocess Task("qa-flaky-detector", {test_paths})
    # verify flaky_detection.json on disk
    # retry once if missing

def phase_5_5_learnings(rc):
    # pure Python — call qa_skills.learnings.persist(...)
    # writes ${project_root}/.qa-skills/learnings.json
    # appends to learnings.log

def phase_6_state_write(rc):
    # subprocess scripts/state_write.py with inputs JSON

def phase_7_quality(rc):
    # subprocess scripts/quality.py
    # patches report-data.json post-hoc OR pre-builds and feeds into Phase 8

def phase_8_build_report(rc):
    # subprocess scripts/build_report.py
    # raises if exit != 0

def phase_8b_html(rc, task_call):
    # Task("qa-html-reporter", {report_data_path, locale})
    # verify report-*.html on disk

def phase_9_final_gate(rc):
    # subprocess scripts/final_gate.py
    # warnings appended; never aborts
```

### 5.2 `qa_skills/learnings.py` — verify it can be called as a function (not only LLM)

Current `qa_skills/learnings.py` may or may not expose a clean entry. Audit:
- If `persist(all_test_outputs, project_root, run_id, ...)` exists → use it.
- If not → extract from `qa-coverage-reporter.md` Phase 5.5 spec, implement, pytest.

### 5.3 Delete `agents/qa-coverage-reporter.md`

After Step D acceptance only. Until then keep it; just route around it.

### 5.4 Tests added

**`qa_skills/tests/test_qa_run.py`** — +50 LOC:
- `test_phase_5_runs_flaky_detector`
- `test_phase_5_5_learnings_writes_json_and_log`
- `test_phase_6_state_write_runs`
- `test_phase_8_build_report_runs`
- `test_phase_8_rejects_report_when_wrapper_exits_nonzero`
- `test_phase_8b_html_renders_html`
- `test_phase_9_final_gate_records_warnings_only`

If `qa_skills/learnings.py` needs new entry → +30 LOC `test_learnings.py`.

### 5.5 Acceptance for Step D

- pytest → ~295 green
- Driver run end-to-end produces:
  - `report-data.json` v2 (schema-gated)
  - `report-*.html`
  - `learnings.json` with version 1.0
  - `final_gate` warnings (or empty)
- `quality_score` derives from real coverage + real flaky count (no fake 88)

---

## 6. Step E — Cutover (orchestrator becomes a thin wrapper)

**Goal:** `qa-orchestrator` agent invokes `qa_run.py` and returns its JSON. Old MD deleted.

### 6.1 New `agents/qa-orchestrator.md` (~40 lines)

```markdown
---
name: qa-orchestrator
description: Thin LLM wrapper around scripts/qa_run.py — the deterministic QA pipeline driver. All real work happens in Python; this agent translates user-facing input to a single subprocess call and surfaces the final JSON.
model: haiku
tools: Bash, Read
---

You are the QA-Skills orchestrator agent. Your job is single-step:

1. Receive `{project_path, locale, force_full, categories, mode, interactive}` from caller.
2. Build a flat CLI:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/qa_run.py" \
     --project-root "${PROJECT_PATH}" \
     --locale "${LOCALE}" \
     --mode "${MODE}" \
     ${FORCE_FULL:+--force-full} \
     ${CATEGORIES:+--categories "${CATEGORIES}"} \
     ${INTERACTIVE:+--interactive}
   ```
3. Parse JSON stdout. Return verbatim to caller.

# Output

Return whatever `qa_run.py` printed. Do NOT modify, summarize, or wrap.

# Hard rules

- Never call Task tool. Never invoke sub-agents directly. `qa_run.py` does that.
- Never read or write `report-data.json`, `test-state.json`, or any file under `tests/`.
- Never compute coverage, quality, or any aggregation.
- Never re-implement banners — `qa_run.py` emits them.
- Non-zero exit from the script → return `{"status":"error","reason":"<stderr summary>"}`.
```

### 6.2 Driver emits user-facing banners

Move banner emission **into `qa_run.py`** (Python `print` to stdout). The skill catches and displays.

### 6.3 Delete (replaced):

- `agents/qa-coverage-reporter.md`
- `skills/coverage-reporter/SKILL.md` (if it exists) → check and delete
- `RUNTIME_ENFORCEMENT_PLAN.md`
- `STUB_FIX_PLAN.md`

### 6.4 Acceptance for Step E

- pytest → still ~295 green
- Real run on `Candidate_Mngmnt`:
  - all `logs/<run_id>/` artifacts present (12+ files)
  - `report-data.json` is v2 with non-empty `execution` blocks
  - `quality_score` reflects real failures (likely lower than 88, that's correct)
  - `coverage_by_category[*].stub_files` populated if any
  - tests look domain-driven, no "Generate all remaining"

### 6.5 Rollback

If Step E breaks: orchestrator MD is git-tracked; revert single file restores LLM-orchestrator. `qa_run.py` stays in tree, unused. Re-run.

---

## 7. Step F — Docs + cleanup

### 7.1 README.md update

Replace architecture diagram. Add §How it works:
- "QA-Skills v2 uses a Python driver (`qa_run.py`) to coordinate 7 bounded LLM sub-agents. Each sub-agent has one job at one scope. The driver owns sequencing, verification, execution, and reporting."

### 7.2 New `ARCHITECTURE.md`

Distilled version of `ARCHITECTURE_DIAGNOSTIC.md` + this plan. ~200 lines.

### 7.3 CHANGELOG.md

```markdown
## v2.0.0 — 2026-05-1X
### Changed (BREAKING)
- Pipeline rewritten as Python-driven. `qa-orchestrator` agent shrunk from 880 → 40 lines.
- `qa-coverage-reporter` agent removed; report assembly is now `scripts/build_report.py`.
- All test-gen sub-agents receive one file per Task call (was: 10–47).
- `domain_brief_<cat>.json` is now mandatory; pipeline retries on missing.

### Added
- `scripts/qa_run.py` — pipeline driver.
- `qa_skills/driver.py`, `qa_skills/prompt_builder.py`.
- End-to-end pytest (`test_qa_run.py`).

### Removed
- `agents/qa-coverage-reporter.md`.
- `RUNTIME_ENFORCEMENT_PLAN.md`, `STUB_FIX_PLAN.md` (superseded).
```

### 7.4 Final pytest target

**~300 tests green.**

---

## 8. Order of execution (linear)

| Step | Hours | Output                                                                 |
|------|-------|------------------------------------------------------------------------|
| A    | 3     | Driver Phase 0/1/2 + tests. Pytest 255.                                |
| B    | 2     | Phase 2.7 domain learn forced. Pytest 260.                             |
| C    | 6     | Phase 3 file-per-Task + 6 sub-agent MD shrinks + tests. Pytest 285.    |
| D    | 3     | Phases 5/5.5/6/7/8/8b/9 + tests. Pytest 295.                           |
| E    | 1     | Cutover orchestrator. Delete coverage-reporter. Real run.              |
| F    | 1     | Docs, CHANGELOG, ARCHITECTURE.md.                                      |

Total: **~16 hours of focused work** (2 working days).

---

## 9. Acceptance — full-system

Re-run on `Candidate_Mngmnt` produces:

| Check                                                | Pass when                                              |
|------------------------------------------------------|--------------------------------------------------------|
| `report-data.json` exists and `version == "2.0"`     | yes                                                    |
| `coverage_by_category[*]` has 7 keys                 | `{pct, covered_items, missing_items, total, files, stub_files, status}` |
| `coverage_by_category[*].execution` has runner data  | total/passed/failed/duration_ms present                |
| `logs/agent_output_*.json` × 6                       | exists, merged                                         |
| `logs/execution_*.json` × 6                          | exists, exit_code reflects reality                     |
| `logs/domain_brief_*.json` × 6                       | exists OR `warnings: domain_brief_unavailable:<cat>`   |
| `logs/batch_state.json`                              | exists, every batch marked completed                   |
| `logs/warnings.json`                                 | exists                                                 |
| `tests/api/**/*.test.ts` content                     | references domain_brief hints; assertions are specific, not `[200,403].toContain` |
| No "Generate all remaining" anywhere in artifacts    | confirmed                                              |
| `quality_score`                                      | reflects real failures (likely 40–70, not fake 88)     |
| Stub markers detection                               | 0 files match STUB_MARKERS                             |
| pytest                                               | ~300 green                                             |

---

## 10. Open decisions before Step A

| Decision | Default | Override if |
|---|---|---|
| Task subprocess CLI shape | `claude -p "<agent>" --input-json -` (one-shot, JSON stdout) | Anthropic CLI differs — discover empirically at Step A end |
| Per-batch parallelism | 3 (matches `qa_skills.budget.MAX_PARALLEL_BATCHES_PER_CATEGORY`) | Bench shows different optimum |
| Domain analyzer chunk size | 8 files | User reports brief gen failing on large chunks |
| Reference patterns: agent reads from disk vs. embedded in prompt | Read from disk (cheaper) | If reference path resolution flakes |
| `qa-html-reporter` stays as LLM agent | yes (it does locale-aware rendering well) | If rendering bugs persist post-cutover |

---

## 11. Definition of done

1. All §9 acceptance checks pass on Candidate_Mngmnt.
2. `pytest` ~300 green, zero flaky.
3. Run completes in < 30 minutes on Candidate_Mngmnt (current run took ~37 min and produced trash).
4. `ARCHITECTURE.md` reads as ground truth; no contradictions with code.
5. `git log --oneline` reads as a clean sequence of A→B→C→D→E→F.

---

## 12. What we explicitly are NOT doing in v2

- Not rewriting `qa-code-analyzer`, `qa-env-validator`, `qa-flaky-detector`, `qa-git-diff-analyzer`, `qa-html-reporter`, `qa-learnings-validator`. They already work at correct scope.
- Not changing the analysis schema.
- Not changing `reference/*.md` test patterns.
- Not changing `test-orchestrator` skill (trigger surface stays).
- Not changing CLI args of any existing `scripts/*.py`.
- Not adding new LLM models or per-call model overrides.
- Not adding parallel-across-categories (already supported via budget windows; no new feature).

---

## Approval needed before Step A

User confirms:
- §1 file inventory accurate
- §2–§7 step ordering acceptable
- §10 defaults acceptable
- §9 acceptance checks complete and sufficient

On approval → start Step A.
