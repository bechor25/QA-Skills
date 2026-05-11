# RUNTIME_ENFORCEMENT_PLAN — Track C

> Status: PROPOSED — not yet executed
> Trigger: Second run on `Candidate_Mngmnt` (run_id `ff5143c0-…`). 199 real files generated (Track A worked — 0 stubs) BUT three runtime gaps surfaced:
> 1. **Quality is shallow.** Generic "401 without auth" repeated 36× across api category. No happy-path, no validation depth, no business-logic coverage.
> 2. **Tests are not executed.** `timeline` shows only scan / strategy / dispatch; `execution_results = {}`. Sub-agents report `status: passed` without running anything.
> 3. **report-data shape diverges from `qa_skills.report_builder`.** Coverage block is v1 `{pct, tests, status}` instead of v2 `{pct, covered_items, missing_items, total, files, stub_files, status}`. `quality_score: 88` is fake-green; B2 stub-awareness, B4 telemetry, A5.b batching all silent at runtime.
>
> Single root cause: **MD describes a contract; the LLM orchestrator + coverage-reporter improvise around it**. Track A/B Python modules are green (217 pytest) but never invoked at run time. Track C closes the gap.

## Architecture principle (NEW)

**The MD is not a suggestion.** Every Phase-9-equivalent decision (coverage math, report assembly, contract validation) MUST come from a deterministic Python wrapper. LLM agents may *orchestrate* (decide what to do, in what order); they may NOT *compute* (build coverage shapes, decide pass/fail, derive missing_items). Computation belongs to `qa_skills.*` modules invoked via `scripts/*.py` CLI wrappers.

The earlier Phase-9 trim (REFACTOR_PLAN) made Python the source of truth in code. Track C makes Python the source of truth at runtime.

---

## Track C1 — Enforce wrapper-script invocation

**Problem.** `qa-coverage-reporter` LLM rebuilt `report-data.json` manually, ignoring `qa_skills.report_builder.build_report_data`. Result: v1 shape, no `stub_files[]`, no `missing_items[]`, fake `pct: 100`.

**Goal.** Make every deterministic computation step a Bash call to a wrapper script. Sub-agent / orchestrator output without the wrapper-script log line is rejected at the next gate.

### C1.a Missing wrapper — `scripts/build_report.py`

Today `qa_skills.report_builder.build_report_data` is a Python function with no CLI front. Add:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/build_report.py" \
    --run-id "${RUN_ID}" \
    --project-root "${PROJECT_ROOT}" \
    --analysis "${LOGS_DIR}/analysis.json" \
    --logs-dir "${LOGS_DIR}" \
    --strategy "${LOGS_DIR}/strategy.json" \
    --flaky "${LOGS_DIR}/flaky.json" \
    --state "${PROJECT_ROOT}/test-state.json" \
    --out "${PROJECT_ROOT}/test-reports/report-data.json"
```

Wrapper:
1. Reads all `agent_output_<agent>.json` from logs_dir (B4 emits these).
2. Calls `build_report_data(...)`.
3. Writes v2 shape with `coverage_by_category[*]` containing `pct, covered_items[], missing_items[], total, files[], stub_files[]`.

**File:** [skills/_shared/scripts/build_report.py](skills/_shared/scripts/build_report.py) (NEW, ~80 LOC).

### C1.b Orchestrator Phase 6 — replace LLM JSON assembly with Bash call

[agents/qa-coverage-reporter.md](agents/qa-coverage-reporter.md) currently lets the LLM "aggregate" results into report-data. Change to:

```
1. Read all ${LOGS_DIR}/agent_output_*.json.
2. Bash: python3 ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/build_report.py ...
3. Verify exit_code == 0, file exists, schema version == "2.0".
4. Hand off to qa-html-reporter (already wraps html_render.py).
```

Acceptance: post-Phase 6, `report-data.json` MUST have key `version: "2.0"` AND every `coverage_by_category[*]` MUST contain `{pct, covered_items, missing_items, total, files, stub_files, status}`. If any key absent → orchestrator marks `final_status: partial` and warns `report_schema_mismatch`.

### C1.c Sub-agent self-validation gate

Every test-gen agent ([agents/qa-unit-test.md](agents/qa-unit-test.md), api, ui, …) MUST, after Write loop:

```
HARD GATE — before returning AgentResult:
  Bash: echo "$AGENT_RESULT" | python3 ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/validate_test_output.py \
        --language ${analysis.language}
  exit_code != 0  → status: error, reason: validate_test_output_failed
  exit_code == 0  → continue
```

### C1.d Orchestrator post-dispatch hard gate (A2 enforcement)

After each Task call, orchestrator MUST:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/contract_diff.py" \
    --result-json "$AGENT_RESULT_JSON" \
    --expected-files "${LOGS_DIR}/expected_files.json" \
    --category "${CAT}" \
    --language "${LANG}"
# stdout: {"extras": [...], "missing": [...], "violations": [...]}
```

New wrapper [skills/_shared/scripts/contract_diff.py](skills/_shared/scripts/contract_diff.py) (~30 LOC) — thin shell around `validators.validate_agent_result_against_contract`.

Orchestrator MUST then:
- `extras` → delete files, append `path_contract_violation:<path>` warnings.
- `missing` → append to `coverage[cat].missing_items[]`, downgrade `status`.
- `violations` → append `path_regex_violation_<lang>:<path>` warnings.

### Acceptance — Track C1

| Check | Before | After C1 |
|---|---|---|
| `report-data.version` | `null` | `"2.0"` |
| `coverage_by_category[cat]` shape | `{pct, tests, status}` | `{pct, covered_items[], missing_items[], total, files[], stub_files[], status}` |
| `agent_output_<agent>.json` per agent in logs_dir | absent | present (B4 wired via wrapper) |
| `path_contract_violation:` warnings on wrong-named files | absent | present |
| Re-run replay produces identical report (deterministic) | no | yes (same input → same Python output) |

**Effort:** ~150 module/script LOC, ~80 MD edits, ~40 pytest LOC.

---

## Track C2 — Domain Learn (Phase 2.7)

**Problem.** Tests are shallow because sub-agents see only path planner output (route IDs, module paths). They cannot infer business behaviors from a route ID. They fall back to "401 without auth" — the only assertion valid for every endpoint.

**Goal.** Insert a per-category domain-analysis phase between strategy (2.5) and dispatch (3). One LLM agent reads each handler's source, extracts a structured `domain_brief`, persists it, and threads it into the sub-agent input. Sub-agent now generates **per-behavior** tests instead of **per-route** tests.

### C2.a New agent — `qa-domain-analyzer.md`

Read-only LLM agent. Invoked once per planned category. Receives:

```json
{
  "category": "api",
  "language": "typescript",
  "expected_files": [/* slice from compute_expected_files */],
  "analysis_excerpt": {
    "modules":   [/* only modules touched by this category */],
    "routes":    [/* same */],
    "frontend_files": [/* for ui/a11y */]
  },
  "source_root": "${project_root}"
}
```

Steps:
1. For each `expected_files[i]`, locate the source file (`covers[]` paths).
2. Read ≤200 lines per source file (cap context).
3. Extract:
   - **request shape** — body schema refs (`z.object`, `pydantic.BaseModel`, `joi.object`), required vs optional fields, types.
   - **response shape** — success status + payload; error variants + status codes.
   - **middleware chain** — auth gates, RBAC, validation, rate-limit.
   - **DB ops** — read/write/transaction; tables touched.
   - **external calls** — queues, caches, 3rd-party APIs.
   - **explicit error branches** — every `throw`, `return res.status(4xx)`.
4. Emit per file a **behaviors[]** list with `{trigger, expected_outcome, side_effects, error_paths}`.
5. Emit per file a **test_hints[]** list with canonical hint codes:
   - `happy_path`
   - `validation_missing_field:<field>`
   - `validation_wrong_type:<field>`
   - `auth_missing`, `auth_wrong_role:<role>`
   - `db_failure`, `external_failure:<service>`
   - `boundary:<param>`
   - `idempotency`, `concurrency`

Returns:

```json
{
  "agent": "qa-domain-analyzer",
  "category": "api",
  "status": "passed",
  "briefs": [
    {
      "expected_file": "tests/api/auth/login.api.test.ts",
      "covers": ["POST /api/login"],
      "source_files": ["apps/api/src/routes/auth.ts"],
      "behaviors": [
        {
          "trigger": "POST /api/login {email,password}",
          "expected_outcome": "200 with {token, refreshToken, user}",
          "side_effects": ["RefreshToken row created", "auditLog row created"],
          "error_paths": [
            {"trigger": "missing email",     "outcome": "400 ValidationError"},
            {"trigger": "wrong password",    "outcome": "401 InvalidCredentials"},
            {"trigger": "user.mfaEnabled",   "outcome": "200 with {mfaRequired: true}"},
            {"trigger": "5 failed attempts", "outcome": "429 RateLimited"}
          ]
        }
      ],
      "test_hints": [
        "happy_path",
        "validation_missing_field:email",
        "validation_missing_field:password",
        "auth_wrong_credentials",
        "mfa_required_branch",
        "rate_limit_after_5_attempts"
      ]
    }
  ]
}
```

Persist to `${LOGS_DIR}/domain_brief_<category>.json`.

**File:** [agents/qa-domain-analyzer.md](agents/qa-domain-analyzer.md) (NEW, ~90 lines).

### C2.b Thread `domain_brief` into sub-agent input

Orchestrator Phase 3 input builder appends:

```json
"domain_brief": "<slice of domain_brief_<cat>.json for files in this batch>"
```

Sub-agents ([qa-unit-test.md](agents/qa-unit-test.md), [qa-api-test.md](agents/qa-api-test.md), [qa-security-test.md](agents/qa-security-test.md), [qa-contract-test.md](agents/qa-contract-test.md), [qa-ui-test.md](agents/qa-ui-test.md), [qa-a11y-test.md](agents/qa-a11y-test.md)) get a new section:

```
## Behavior-driven generation (REQUIRED)

For each entry in path_contract.expected_files[]:
  1. Locate its brief in input.domain_brief[].
  2. Generate ONE `describe`/`test.describe` block.
  3. Generate ONE `it`/`test` per entry in brief.test_hints[].
  4. Each `it` MUST assert against brief.behaviors[*].expected_outcome,
     not just status code. For error paths, assert error payload shape.
  5. If a hint is "happy_path" — generate the success-path test FIRST.

Forbidden:
  - `expect(res.status).toBeGreaterThanOrEqual(400)` — too loose.
  - Skipping a test_hint without recording reason in skipped_hints[].
  - Asserting only HTTP status without body shape.
```

### C2.c Path-planner uses brief for naming (optional polish)

If `domain_brief[].test_hints` contains a `boundary:<param>` hint, the planner MAY split that route into a separate test file `<route>_boundary_<param>.test.ts`. Out of scope for v1; flagged as v2 candidate.

### C2.d Orchestrator Phase 2.7 dispatch

```python
# Phase 2.7 — Domain Learn (NEW)
for cat in plan["summary"]["categories_planned"]:
    brief = Task("qa-domain-analyzer", build_brief_input(cat, analysis, expected_files[cat]))
    write_json(logs_dir / f"domain_brief_{cat}.json", brief)
```

Briefs are computed ONCE per category and reused across all batches within that category (A5.b windows).

### Acceptance — Track C2

| Check | Before | After C2 |
|---|---|---|
| api/candidates.test.ts: distinct test bodies | 1 (only "401 no auth") | ≥5 (happy + auth + 3 validations + error) |
| Per-file `it` count median | 1-2 | 4-8 |
| Status-only assertions | 100% | ≤30% (rest assert payload shape) |
| `domain_brief_<cat>.json` artifacts in logs | absent | present, one per category |
| Token cost per category | baseline | baseline × 1.3-1.5 (one extra LLM call per category) |
| Wall-time per category | baseline | baseline + ~3-5 min (single Read-heavy LLM call) |

**Effort:** ~250 LOC (new agent.md 90 LOC + orchestrator wiring 60 LOC + sub-agent updates 6×15 LOC + pytest 30 LOC).

---

## Track C3 — Execution telemetry

**Problem.** `execution_results = {}`. `timeline` lacks an execution phase. Sub-agents emit `status: passed` having never invoked the test runner. Failures are invisible until users run `npm test` themselves.

**Goal.** Make test execution **mandatory** and **machine-checked**. Sub-agent that returns `status: passed` without a verified `execution_result` block is rejected as `error: missing_execution_result`.

### C3.a New wrapper — `scripts/run_tests.py`

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/run_tests.py" \
    --category api \
    --project-root "${PROJECT_ROOT}" \
    --files-json "${LOGS_DIR}/agent_output_qa-api-test.json" \
    --out "${LOGS_DIR}/execution_qa-api-test.json"
```

Steps:
1. Detect runner from `analysis.json` (`vitest` / `jest` / `pytest` / `playwright`).
2. Read emitted files from agent_output JSON.
3. Spawn runner with `--reporter=json` (vitest/jest) or `--json-report` (pytest) or `--reporter=json` (playwright). Restrict glob to emitted files only — DO NOT run the entire suite.
4. Parse runner JSON → emit canonical structured result:

```json
{
  "category": "api",
  "runner": "vitest",
  "total": 36,
  "passed": 30,
  "failed": 4,
  "skipped": 2,
  "duration_ms": 18230,
  "failures": [
    {
      "file": "tests/api/candidates/candidates.test.ts",
      "title": "GET /api/candidates returns 200 with paginated list",
      "error": "TypeError: Cannot read properties of undefined (reading 'findMany')",
      "stack_excerpt": "<≤10 lines>"
    }
  ],
  "exit_code": 1
}
```

5. Exit code matches runner exit code (`0` = all pass).

**File:** [skills/_shared/scripts/run_tests.py](skills/_shared/scripts/run_tests.py) (NEW, ~150 LOC).

### C3.b Sub-agent execution gate

Every test-gen agent gets a new **Phase 8 — Execute** section:

```
After Write loop, BEFORE returning AgentResult:

  Bash: python3 ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/run_tests.py \
        --category ${CAT} --project-root ${PROJECT_ROOT} \
        --files-json /dev/stdin --out ${LOGS_DIR}/execution_${AGENT}.json \
        < <(echo "$AGENT_RESULT_JSON_PARTIAL")

  exit_code == 0  → embed execution result in AgentResult.execution_result
                    status = passed
  exit_code != 0  → status = partial
                    Up to 2 fix iterations:
                      - read failures[]
                      - edit the failing test file
                      - re-run
                    After 2 iterations, accept remaining failures and surface them.

Sub-agent that returns status=passed WITHOUT execution_result block →
orchestrator rejects with error: missing_execution_result.
```

### C3.c Orchestrator timeline + report fields

`build_report_data` (C1.a) reads `execution_<agent>.json` files from logs_dir and:
- adds `coverage_by_category[cat].execution = {total, passed, failed, skipped, duration_ms}`.
- prepends a "Test execution" section to HTML report with per-category bars (green/red by `failed > 0`).
- adds `timeline.execution = {start, end}`.

### C3.d UI/a11y guardrail

`qa-ui-test` and `qa-a11y-test` run Playwright which requires a live server. C3.a runner detection MUST check `server_plan.url` reachability before spawning Playwright. Unreachable → execution_result.status = `skipped:server_unreachable` (does NOT propagate to AgentResult.status — the test files still ship, but flagged as unexecuted).

### Acceptance — Track C3

| Check | Before | After C3 |
|---|---|---|
| `execution_results.<cat>.total` | absent / empty | int matching file count |
| `timeline.execution` | absent | present with start/end |
| Sub-agent `status: passed` without ran tests | accepted | rejected `error: missing_execution_result` |
| Failing tests visible in HTML report | no | yes (red bar + failures list) |
| 2-iteration self-fix when runner reports failures | no | yes |

**Effort:** ~250 LOC (`run_tests.py` 150 LOC + sub-agent MD updates 6×20 LOC + html_render extension 30 LOC + pytest 40 LOC).

---

## Track C totals

| Track | New LOC | MD LOC | Pytest LOC | Total |
|-------|---------|--------|------------|-------|
| C1 (enforcement)   | 150 | 80  | 40 | 270 |
| C2 (domain learn)  | 120 | 130 | 30 | 280 |
| C3 (execution)     | 150 | 120 | 40 | 310 |
| **Total**          | **420** | **330** | **110** | **860 LOC** |

## Hard rules across Track C

1. **No project-specific code.** All wrappers operate on `analysis.json` + JSON inputs. Adding QA-Skills to a new project requires zero edits inside `qa_skills/*`.
2. **All computation in Python, all orchestration in MD.** No JSON shape decisions inside LLM agents.
3. **Every Bash gate uses `${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/*.py`.** No inline python -c, no inline shell math.
4. **Sub-agent return values are immutable contracts.** Once written, orchestrator may diff/reject/aggregate but never edit.

## Execution order

1. **C1.a** — `scripts/build_report.py` wrapper. Foundation.
2. **C1.b** — `qa-coverage-reporter.md` change to Bash-only. Coverage now uses Python.
3. **C1.c** + **C1.d** — sub-agent and orchestrator self-validation gates. Closes A2 + B1 runtime.
4. **C3.a** — `scripts/run_tests.py`. Independent of C2, foundational for trust.
5. **C3.b/c** — Sub-agent execution gate + report fields.
6. **C2.a** — new `qa-domain-analyzer` agent.
7. **C2.b** — sub-agent behavior-driven generation. Quality lift.
8. **C2.d** — orchestrator Phase 2.7 wiring.

## Acceptance — Candidate_Mngmnt re-run after Track C

| Metric | After Track A+B (today) | After Track C |
|--------|-------------------------|---------------|
| Stub files | 0 | 0 (unchanged) |
| Real files | 199 | ≤199 (any rejected by C1.c/d removed) |
| `report-data.version` | `null` | `2.0` |
| `coverage_by_category[*]` v2 keys present | no | yes |
| `quality_score` honest | 88 (lie) | computed from real coverage + execution_results |
| Tests executed | no | yes — `execution_results.<cat>` populated |
| Failing tests visible | no | yes — HTML red bars |
| Test bodies per route (api) | 1 | ≥5 (happy + ≥3 error paths + validation) |
| `domain_brief_<cat>.json` | absent | present |
| `agent_output_<agent>.json` | absent | present (B4 wired) |
| `path_contract_violation:` warnings | absent | present when applicable |

## Risk

- **C2 cost.** One extra LLM call per category (`qa-domain-analyzer`). Token budget +~5K per category, wall-time +3-5 min. Mitigation: domain_brief cached in logs; subsequent runs on unchanged modules skip re-analysis (use `git_diff_class` from `qa_skills.git_diff`).
- **C3 runner detection.** Polyglot repos (Python backend + TS frontend) may need two runner invocations per run. Mitigation: `analysis.language` determines primary; sub-agent's `category` determines if frontend runner (Playwright) is also needed.
- **C1.b backwards compat.** Existing `qa-coverage-reporter` agent users who scripted around the old v1 report-data shape break. Mitigation: bump `version: "2.0"` is explicit signal; agents already check for it.

Plan ends.
