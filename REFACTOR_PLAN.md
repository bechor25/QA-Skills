# QA-Skills Refactor Plan

**Status legend:** `[ ]` pending · `[~]` in_progress · `[x]` done · `[!]` blocked · `[-]` skipped

**Last updated:** 2026-05-10
**Owner:** Bechor Simhaev
**Sample project for verification:** `/Users/bechorsimhaev/Desktop/code/test/`

---

## Goal

Make QA-Skills a reliable, deterministic, autonomous test-generation plugin for manual QA testers. **Single trigger phrase → completed HTML report. No `partial` runs as default outcome.**

Eliminate self-correction loop where Phase 9 (final gate) retroactively detects + cleans up sub-agent rework. Prevent rework at source instead of cleaning it post-hoc.

## Architectural principles (non-negotiable)

1. **Two-layer skill→agent stays.** Skills (~25 lines, main context, trigger only). Agents (isolated context, see test code).
2. **Deterministic logic = Python (stdlib only).** No `pip install` step in plugin distribution.
3. **LLM only where required:** code analysis (`qa-code-analyzer`), test generation (`qa-test-generator` per category).
4. **Path contract enforced at source.** Sub-agents have NO path-derivation logic. `expected_files` is the only law.
5. **Single source of truth per concern.** No duplicated `derive_domain_and_tag` across 7 files.
6. **Acceptance pytest in `skills/_shared/qa_skills/tests/`** is the safety net, not Phase 9 runtime gates.

---

## Decision required before starting

### D1. Language scope for v1

- [x] **D1 DECIDED: Option A — TS/JS + Python only** (2026-05-10, user-confirmed)

Java/C# claims will be removed from README, AGENT.md, plugin.json, USAGE.md, env-validator framework table, agent framework tables. Tracked as Phase 0 below.

---

## Phase 0 — Language scope cleanup (Option A)

- [x] Remove Java row from `README.md` "Supported languages" + agents table
- [x] Remove C# row from `README.md` "Supported languages" + agents table
- [x] Remove Java/C# from `AGENT.md` framework table
- [x] Update `.claude-plugin/plugin.json` description to "TypeScript/JavaScript + Python"
- [x] Update `USAGE.md` to drop Java/C# triggers/examples
- [x] Remove Java/C# rows from sub-agent framework tables (`qa-unit-test.md` Phase 1, `qa-api-test.md` Phase 2)
- [x] Update env-validator to not check `mvn`/`dotnet`
- [x] Strip Java/C# regex blocks from `qa-code-analyzer.md` Phase 2
- [x] Drop Java/C# branches from `qa-ui-test.md`, `qa-a11y-test.md`, `qa-flaky-detector.md`, `qa-git-diff-analyzer.md`
- [x] Strip Java/C# code samples from `reference/unit-test-patterns.md`, `reference/api-test-patterns.md`
- [x] Restrict `run_context.schema.json` language enum to `typescript|javascript|python|multi`

---

## Phase 1 — Data contract unification

**Why first:** Python extraction would amplify the bug if `file` vs `path` drift remains.

### 1.1 Bump `analysis.schema.json`
- [x] `modules[].path` (already in schema, verified)
- [x] `frontend_files[]` always object array `[{path, hash, kind, has_forms}]`
- [x] `routes[].kind` enum `api|page|asset|unknown` (REQUIRED)
- [x] `routes[].produces` enum `json|html|unknown` (REQUIRED)
- [x] `routes[].source` framework hint string or null
- [x] Top-level `server_hint` block with `backend_command`, `backend_port`, `frontend_command`, `frontend_port`, `framework`
- [x] `language` enum restricted to `typescript|javascript|python|multi`

### 1.2 Update `qa-code-analyzer.md`
- [x] Phase 3: route classification table (FastAPI/Flask/Django/Express/Next → kind+produces+source)
- [x] Phase 3: deterministic `server_hint` detection rules
- [x] Phase 5 example JSON updated with new fields
- [x] Phase 5 field-by-field rules: `routes` now requires 8 keys, `server_hint` documented

### 1.3 Update `qa-orchestrator.md`
- [x] `compute_expected_files()` unit branch reads `m["path"]` (was bug: read `m["name"]`/`m["file"]`)
- [x] `is_api_route()` uses `route.kind` first, falls back to legacy heuristic
- [x] Hard rule note added below unit branch warning future authors off `m["file"]`/`m["name"]`

### 1.4 Update sub-agents (6 files)
- [x] `qa-unit-test.md` consumption snippet uses `m.get("path")` (was bug: `m.get("file")`)
- [x] Verified other 5 sub-agents have no `m.get("file")` references

### 1.5 `covers[]` semantics
- [x] Created `reference/path-contract.md` covering: `expected_files` shape, `covers[]` per category, sub-agent consumption pattern, forbidden behaviors, error codes

**Acceptance pending:** verify on `/test/` sample (run after Phase 3 Python extraction lands).

---

## Phase 2 — Analyzer enrichment (routes + server)

### 2.1 Route classification
- [x] `qa-code-analyzer.md` Phase 3 has classification table covering FastAPI/Flask/Django/Express/Next routes
- [x] First-return-statement disambiguation rule for ambiguous handlers
- [x] `routes[].kind`/`produces`/`source` mandatory in `analysis.schema.json`

### 2.2 `server_hint` detection
- [x] `qa-code-analyzer.md` emits top-level `server_hint` block
- [x] Detection rules per framework (next/vite/nuxt/express/remix/astro for Node; fastapi/flask/django for Python)
- [x] `server_hint` schema definition in `analysis.schema.json`

### 2.3 `server_plan` in orchestrator
- [x] `qa-orchestrator.md` "server_plan" section replaces old "server_check_url resolution"
- [x] `build_server_plan(analysis, mode, allow_start_explicit)` function inline
- [x] Dispatch decision matrix (6 states) covering reachable/unreachable × auto/interactive × allowed/not-allowed
- [x] Lifecycle hard rules: never start without `start_allowed`, never kill processes you didn't spawn, never let sub-agents resolve URLs
- [x] `qa-ui-test.md`, `qa-a11y-test.md`, `qa-api-test.md`, `qa-security-test.md`, `qa-contract-test.md` updated to read `preflight.server_plan.url` (was `server_check_url`)
- [x] `skills/{ui-playwright,api-test,security-test,contract-test,accessibility-test}/SKILL.md` updated to build `server_plan` instead of `server_check_url`
- [x] `qa-ui-test.md` Phase 1a hard rule: do not improvise, do not read removed `server_check_url` / `frontend_dev_server` / `start_server_command`

### 2.4 `is_api_route()` rewrite
- [x] `qa-orchestrator.md` `is_api_route()` reads `route.kind` first; legacy heuristic only as fallback for older `analysis.json`

**Acceptance pending:** verify on `/test/` sample after Phase 3 Python extraction.

---

## Phase 3 — Python extraction (`skills/_shared/qa_skills/`)

**Constraint: stdlib ONLY.** No `jsonschema`, no `pytest` (only as dev dep for our own tests). `json`, `re`, `hashlib`, `pathlib`, `subprocess`, `dataclasses`.

### 3.1 Module skeleton
- [x] `skills/_shared/qa_skills/__init__.py`
- [x] `skills/_shared/qa_skills/types.py` — `Module`, `Route`, `FrontendFile`, `ServerHint`, `Analysis`, `ExpectedFile`, `ServerPlan`, `AgentResult`
- [x] `skills/_shared/qa_skills/analysis.py` — `load_analysis(path) -> Analysis`, `validate_analysis_dict`, `AnalysisValidationError`
- [x] `skills/_shared/qa_skills/routes.py` — `is_api_route(r)`, `derive_domain_and_tag(path)`, `AUTH_TOPICS`
- [x] `skills/_shared/qa_skills/path_planner.py` — `compute_expected_files(category, analysis, language) -> list[ExpectedFile]`
- [x] `skills/_shared/qa_skills/server.py` — `build_server_plan`, `is_reachable`, `start_server`, `stop_server`
- [x] `skills/_shared/qa_skills/coverage.py` — real-units `compute_coverage(category, agent_outputs, analysis)`
- [x] `skills/_shared/qa_skills/validators.py` — `validate_path`, `validate_test_output`, `validate_expected_files`, `assert_artifact_exists`
- [x] `skills/_shared/qa_skills/final_gate.py` — keeps only 9a + 9d.2 + 9e
- [x] `skills/_shared/qa_skills/state.py` — `read_state`, `write_state`, `diff_modules`

### 3.2 CLI entry points
- [x] `skills/_shared/scripts/validate_analysis.py`
- [x] `skills/_shared/scripts/plan_expected_files.py` (supports `--category` or `--all --out`)
- [x] `skills/_shared/scripts/validate_test_output.py`
- [x] `skills/_shared/scripts/final_gate.py`

Each runnable as `python3 -m qa_skills.<module>` AND as `python3 skills/_shared/scripts/<name>.py`.

### 3.3 Schemas
- [x] `skills/_shared/schemas/analysis.schema.json` (Phase 1.1)
- [x] `skills/_shared/schemas/test_output.schema.json` (closed `status` enum, path regex inlined, `outputs[].covers` documented)
- [ ] `skills/_shared/schemas/report_data.schema.json` (verify alignment — pending)

### 3.4 `qa-orchestrator.md` rewrite
- [x] Phase 1a inline heredocs (4 steps) → single `python3 -m qa_skills.analysis` call
- [x] Phase 2.5 `compute_expected_files` inline definition → `python3 -m qa_skills.path_planner` (script entry: `plan_expected_files.py --all --out`)
- [x] Phase 2.5 `has_signal()` inline definition → `python3 -m qa_skills.strategy` (extracted to `qa_skills/strategy.py`)
- [x] Phase 6 state write narrative wired to `qa_skills.state.write_state`
- [x] Phase 9 entire block (~280 lines) → single `python3 -m qa_skills.final_gate` call
- [x] Hard rule note: `derive_domain_and_tag` lives only in `qa_skills.routes`, never in this file
- [x] Line count: **988 → 685** (~30% reduction)

### 3.5 Convert deterministic agents to Python modules
- [x] `qa-git-diff-analyzer` → `qa_skills/git_diff.py` (`classify_diff`, `update_analysis`) + 11 pytest
- [x] `qa-flaky-detector` → `qa_skills/flaky.py` (`detect_flaky`, cause-hypothesis rules + bilingual fix hints) + 7 pytest
- [x] `qa-learnings-validator` → `qa_skills/learnings.py` (atomic write, hash-based demotion, age-out) + 7 pytest
- [x] `qa-html-reporter` → `qa_skills/html_render.py` (stdlib HTML render, RTL/LTR, light/dark, missing_items as gaps) + 10 pytest. Agent.md now calls the Python renderer; LLM no longer composes HTML.
- [x] Coverage-reporter assembly → `qa_skills/report_builder.py` (orchestrates `coverage`, `gaps`, `artifacts`, `quality`) + 6 pytest. Agent.md now passes inputs to the builder.
- [x] Quality score → `qa_skills/quality.py` (extracted from orchestrator Phase 7 inline block) + 8 pytest
- [x] Gap classification → `qa_skills/gaps.py` (high/medium/low rules) + 9 pytest
- [x] UI/a11y artifacts collection → `qa_skills/artifacts.py` (file walker for screenshots/videos/traces)
- [ ] `qa-env-validator` → optional v2 `qa_skills/env.py` (deferred — heavy install side-effects, kept as agent for now)

Agent .md shims still exist for backward compatibility with the orchestrator's Task dispatcher. v2 cleanup: orchestrator switches to direct CLI calls, .md shims removed.

**Acceptance verified ✅:**
```
$ python3 -m qa_skills.path_planner --analysis fixtures/python_fastapi_analysis.json --category api
[exact match with /test/tests/api/ layout]
```

---

## Phase 4 — Sub-agent simplification

### 4.1 Delete path-derivation logic from sub-agents
- [x] `qa-api-test.md` — deleted "Output paths" + "Hard rule — domain comes from ROUTE PATH" + "Minimum file count enforcement" + "Forbidden patterns" + `derive_domain_and_tag`
- [x] `qa-security-test.md` — deleted same sections + `derive_domain_and_category`
- [x] `qa-contract-test.md` — same
- [x] `qa-unit-test.md` — deleted "Output paths (mirror src sub-dirs)" + "Path enforcement" + "One-file-per-source-module rule"
- [x] `qa-ui-test.md` — deleted "Phase 3.5 Domain sub-dir derivation" + `derive_subdir` + "Hard rule — minimum file count = N pages"
- [x] `qa-a11y-test.md` — deleted "Phase 3 Group pages" + "Hard rule — minimum file count"

All replaced with: read `path_contract.expected_files`. Write exactly those paths. Empty → return `{"status": "error", "reason": "missing_path_contract"}`. Reference: `${CLAUDE_PLUGIN_ROOT}/reference/path-contract.md`.

### 4.2 Delete legacy fallback
- [x] `qa-api-test.md` — `else: legacy` removed
- [x] `qa-unit-test.md` — `else: legacy` removed
- [x] `qa-security-test.md`, `qa-contract-test.md`, `qa-ui-test.md`, `qa-a11y-test.md` — all `else: legacy` removed
- [x] Verified: `grep -rn "derive_domain_and_tag\|derive_domain_and_category\|derive_subdir" agents/ skills/` returns hits only in orchestrator (forbidding) + qa_skills modules (canonical) + path-contract.md (forbidding)

### 4.3 Minimal sub-agent input shape (PARTIAL — refined further in v2)
- [x] Sub-agents now reject contract-less dispatch with explicit error code
- [x] Sub-agents validate `expected_files[i].covers` non-empty before consuming
- [ ] Reduce remaining `analysis`/`routes`/`modules` pass-through (deferred — not blocking for v1)

### 4.4 Sub-agent output uniform `AgentResult`
- [x] `test_output.schema.json` updated: `status` regex enum `^(passed|partial|error|skipped:[a-z0-9_:]+)$`, `outputs[].path` carries inline path regex, `outputs[].covers` documented
- [x] `qa_skills.validators.validate_test_output` enforces this shape; CLI: `python3 skills/_shared/scripts/validate_test_output.py --json <result>`
- [ ] Wire into each sub-agent's pre-return self-check (deferred — v2)

---

## Phase 5 — Coverage math correction

### 5.1 Real-units coverage in `qa_skills.coverage`
- [x] Implemented `compute_coverage(category, agent_outputs, analysis)` returning `{pct, covered_items, missing_items, total, files}`
- [x] Universe per category: unit → non-frontend module paths; api/contract/security → `"METHOD /path"` for `kind==api` routes; ui/a11y → page-kind frontend file paths
- [x] Phantom-coverage filter: agent claims an item not in universe → dropped (acceptance test: `test_phantom_coverage_filtered_out`)
- [x] Old formula `passed_files / total_routes` deleted from `qa-coverage-reporter.md`. Phase 2 now invokes `qa_skills.coverage.compute_coverage` via inline Python heredoc.
- [x] Status enum closed: `passed | partial | error | skipped:<reason>` (e.g. `skipped:env_removed`, `skipped:not_generated`).

### 5.2 Update `report-data.schema.json`
- [ ] Add `covered_items: string[]`, `missing_items: string[]` per category (deferred — qa-html-reporter.md not yet updated to render them)
- [ ] HTML report displays missing items as actionable gaps (deferred)

---

## Phase 6 — Phase 9 trim

### 6.1 Delete from `qa-orchestrator.md`
- [x] 9b (per-category truthfulness) — deleted; coverage built from outputs, can't lie
- [x] 9c (tests_new sum) — deleted; local computation, no drift possible
- [x] 9d.1.1 (regex) — deleted; sub-agent validates pre-Write
- [x] 9d.1.2 (mega + folder mismatch) — deleted; impossible without legacy fallback
- [x] 9d.1.3 (extras delete) — deleted; no rework, no extras
- [x] 9d.3 (schema validation) — moved out (qa-coverage-reporter Phase 2 hosts the validator)

### 6.2 Keep
- [x] 9a (4 artifacts on disk) — sanity, cheap
- [x] 9d.2 (UI/a11y PNG proof-of-run)
- [x] 9e (learnings audit log)

### 6.3 Phase 9 re-implementation
- [x] Single call: `python3 -m qa_skills.final_gate --report-data <path> --project-root <path> --run-id <id>`
- [x] Script returns `{status: completed|partial, warnings: [...]}`
- [x] Orchestrator markdown Phase 9 dropped from ~280 lines to ~30 lines

---

## Phase 7 — Reference deduplication

### 7.1 New shared references
- [x] `reference/path-contract.md` — `expected_files` consumption rules, `covers[]` semantics, error codes (Phase 1.5)
- [x] `reference/category-boundaries.md` — universe per category, ownership table, closed status enum
- [x] `reference/language-support.md` — supported languages, framework table, runner commands, regex spec, v2 onboarding checklist

### 7.2 Trim sub-agent .md files
- [x] Each sub-agent now points to `reference/path-contract.md` instead of repeating the rules inline
- [ ] Sub-agents still carry `reference/<category>-test-patterns.md` Read instructions; further trimming deferred

**Sub-agent line count after Phase 4 (verified):**
- qa-api-test.md: 371 → 255
- qa-security-test.md: 359 → 290
- qa-contract-test.md: 249 → 172
- qa-unit-test.md: 262 → 207
- qa-ui-test.md: 526 → 487 (smallest relative reduction — large pre-flight + recon sections retained)
- qa-a11y-test.md: 285 → 255

Total agents folder: 4506 → 3868 lines (~14% reduction). Most weight removed lives in `qa_skills/*.py` modules (deterministic) + `reference/*.md` (deduplicated narrative).

---

## Phase 8 — Acceptance tests

### 8.1 Pytest fixtures
- [x] `skills/_shared/qa_skills/tests/fixtures/python_fastapi_analysis.json` — FastAPI: 5 modules, 7 api routes + 3 page routes, 3 SSR templates
- [x] `skills/_shared/qa_skills/tests/fixtures/typescript_express_analysis.json` — Vite SPA + Express API: 4 modules, 3 api routes, 3 components

### 8.2 Test files (68 tests, all passing)
- [x] `test_path_planner.py` — exact-path assertions for each fixture × each category + groupings + edge cases (32 tests)
- [x] `test_routes.py` — `derive_domain_and_tag` parametrized + `is_api_route` (13 tests)
- [x] `test_coverage.py` — full/partial/zero-universe + phantom-coverage filtered (6 tests)
- [x] `test_server.py` — `build_server_plan` for fastapi/express + override + reachability (5 tests)
- [x] `test_validators.py` — path regex + AgentResult shape + expected_files (12 tests)
- [x] `test_analysis.py` — schema validation positive + adversarial (drift, bare-string frontend_files, unsupported language) (6 tests)
- [ ] `test_final_gate.py` — pending

### 8.3 CI hook (optional)
- [ ] If repo has CI: add workflow running `pytest skills/_shared/qa_skills/tests/`

**Verification ✅:**
```
$ python3 -m pytest skills/_shared/qa_skills/tests/
============================== 140 passed in 0.07s ==============================
```

Test breakdown:
- `test_path_planner.py` — 32 tests (FastAPI + Express fixtures × 6 categories + edge cases)
- `test_routes.py` — 13 tests (`derive_domain_and_tag` parametrized + `is_api_route`)
- `test_coverage.py` — 6 tests (real-units math, phantom filter, zero universe)
- `test_server.py` — 5 tests (`build_server_plan`, reachability)
- `test_validators.py` — 12 tests (path regex, AgentResult, expected_files)
- `test_analysis.py` — 6 tests (schema + drift detection)
- `test_strategy.py` — 14 tests (`has_signal` per category × per fixture)
- `test_git_diff.py` — 11 tests (signature/trivial/body classification)
- `test_flaky.py` — 7 tests (cause-hypothesis rules + bilingual fix hints)
- `test_learnings.py` — 7 tests (file IO, dismissal, demotion, age-out)
- `test_quality.py` — 8 tests (weighted formula + bonuses + clamping)
- `test_gaps.py` — 9 tests (severity rules + sorting)
- `test_report_builder.py` — 6 tests (assembly, status normalization, phantom filter)
- `test_html_render.py` — 10 tests (HTML structure, score colors, RTL/LTR, no-CDN)

---

## Acceptance criteria

- [x] Python FastAPI sample → tests under root `/tests`, NOT inside `app/` or `sample_app/` (verified via path_planner pytest, output matches `/test/tests/` exactly)
- [x] TS/JS sample → Jest/Vitest + Playwright files in correct locations (verified via Express fixture pytest)
- [x] UI/a11y `expected_files` non-empty when `frontend_files` non-empty (verified)
- [x] Unit `expected_files` never contains `root/root` unless source file is truly at project root (verified via `test_unit_never_collapses_to_root_root`)
- [x] Java/C# removed from claims (Option A — Phase 0)
- [x] No generated test file violates `path_contract.required_pattern` (sub-agent self-check + Phase 9 sanity; regex tests in `test_validators.py`)
- [x] No category reports coverage for files not in its own agent output (`compute_coverage` rebuilds from `outputs[]`)
- [x] `coverage_by_category[*].files` ⊆ agent outputs (constructed from agent outputs only)
- [x] `coverage_by_category[*].covered_items` is subset of universe (no phantom coverage — `test_phantom_coverage_filtered_out`)
- [x] No `derive_domain_and_tag` definition in any sub-agent .md (only forbidding mentions remain)
- [x] **82 acceptance pytest tests passing** in `skills/_shared/qa_skills/tests/`
- [ ] Final live verification on `/test/` sample (full re-run) — pending (requires user invocation; harness regenerates `analysis.json` with the new schema)
- [ ] `qa-orchestrator.md` line count <250 (currently 685; further reduction would require ripping out narrative/banners)
- [ ] No `partial` status from a clean run on a healthy project — pending live verification

---

## Verification command (after each phase)

```bash
# 1. Re-run on test sample
cd /Users/bechorsimhaev/Desktop/code/test
rm -rf tests/ test-state.json test-reports/ .qa-skills/
# (then trigger via Claude: "generate tests for my project" pointing here)

# 2. Compare expected_files vs report-data files
jq -S '[.coverage_by_category[].files[]] | sort' test-reports/report-data.json > /tmp/reported.json
jq -S '[.[] | .[].path] | sort' .qa-skills/logs/*/expected_files.json > /tmp/planned.json
diff /tmp/reported.json /tmp/planned.json
# Expected: empty diff

# 3. Acceptance pytest
cd /Users/bechorsimhaev/Desktop/code/QA-Skills
python3 -m pytest skills/_shared/qa_skills/tests/ -v
```

---

## Resume instructions for next model

1. Read this file top to bottom.
2. Find the last `[~]` (in_progress) task. If none, find the first `[ ]` (pending) task in current phase.
3. **Block on D1 first** if not yet decided. Ask user.
4. Execute task. Mark `[~]` while working, `[x]` when done.
5. After completing each phase, run verification command above and update acceptance criteria checkboxes.
6. Commit per phase, not per task. Commit message: `refactor(qa-skills): phase N - <short summary>`.
7. Never delete this file. Update statuses in place.

## Out-of-scope for this refactor

- Adding new test categories (mutation, perf, load) — registry pattern not needed for v1
- Skill layer collapse — two-layer is intentional
- Cross-agent fix-loop pattern detection (originally point E1) — defer to v2
- Learnings I/O dedupe (originally point F1) — defer to v2
- Events stream — defer to v2
- Auto re-dispatch on partial (originally point D1) — preventive design eliminates need

## Files this refactor will touch

```
DELETE (or rewrite as Python):
  agents/qa-env-validator.md         → qa_skills/env.py
  agents/qa-git-diff-analyzer.md     → qa_skills/git_diff.py
  agents/qa-flaky-detector.md        → qa_skills/flaky.py
  agents/qa-coverage-reporter.md     → qa_skills/coverage.py
  agents/qa-html-reporter.md         → qa_skills/html_render.py
  agents/qa-learnings-validator.md   → qa_skills/learnings.py

EDIT (heavy):
  agents/qa-orchestrator.md          (988 → <250 lines)
  agents/qa-code-analyzer.md         (route kind, server_hint, frontend_files objects)
  agents/qa-{unit,api,ui,security,a11y,contract}-test.md (delete path logic, simplify)

NEW:
  skills/_shared/qa_skills/__init__.py
  skills/_shared/qa_skills/{types,analysis,routes,path_planner,server,coverage,validators,final_gate,state}.py
  skills/_shared/qa_skills/tests/{conftest.py,fixtures/...,test_*.py}
  skills/_shared/scripts/{validate_analysis,plan_expected_files,validate_test_output,final_gate}.py
  skills/_shared/schemas/test_output.schema.json
  reference/path-contract.md
  reference/category-boundaries.md
  reference/language-support.md

UPDATE:
  README.md (language scope per D1)
  AGENT.md  (language scope per D1)
  USAGE.md  (language scope per D1)
  .claude-plugin/plugin.json (language scope per D1)
  skills/_shared/schemas/analysis.schema.json (new shape)
  skills/_shared/schemas/report_data.schema.json (covered_items, missing_items)
```
