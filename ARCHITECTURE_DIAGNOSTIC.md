# QA-Skills — Architecture Diagnostic & Path Forward

**Date:** 2026-05-11
**Run analyzed:** `f6b2d29f-aaf9-41f4-bd8f-067710b5f5ed` on
`/Users/bechorsimhaev/Desktop/code/Candidate_Mngmnt`
**Status:** core architecture broken at scale. Plan deterministic rewrite.

---

## 1. Project goal (restated)

> Skill + agent pipeline that runs a **full QA flow** on a real project in
> common languages (TS/JS, Python). Most target projects are **large** — the
> system must read enough context to understand the domain, build a coherent
> testing strategy, generate quality tests per category (unit/api/ui/sec/a11y/
> contract), execute them, and produce a polished HTML report. Audience is a
> QA team — output must be **trustworthy and demo-able**, not boilerplate.

Two non-negotiables follow:

1. **Domain understanding** — tests must reflect what the code actually does,
   not generic "401 without token" templates.
2. **Execution & honesty** — every passing claim must be backed by a real
   test run; no fake green.

The current implementation fails both at scale.

---

## 2. Run evidence (Candidate_Mngmnt — 70 modules, 6 categories)

### 2.1 What was produced

| Artifact                                 | Present? | Notes                                                 |
|------------------------------------------|----------|-------------------------------------------------------|
| `logs/analysis.json`                     | yes      | Phase 1 (qa-code-analyzer) ran                        |
| `logs/strategy.json`                     | yes      | Phase 2.5 ran                                         |
| `logs/expected_files.json`               | yes      | `plan_expected_files.py` ran                          |
| `logs/flaky_detection.json`              | yes      | Phase 5 ran                                           |
| `test-state.json`                        | yes      | Phase 6 wrapper ran                                   |
| 275 test files on disk                   | yes      | sub-agents wrote files                                |
| `test-reports/report-data.json`          | yes (v1) | **wrong schema** — see §2.3                           |
| `test-reports/report-*.html`             | yes      | rendered from wrong data                              |
| `.qa-skills/checkpoints/run.json`        | yes      | claims `"completed": true, quality_score: 88`         |
| `logs/agent_output_*.json`               | **NO**   | sub-agent returns never persisted                     |
| `logs/execution_*.json` (× 6 categories) | **NO**   | **tests were never executed**                         |
| `logs/domain_brief_*.json` (× 6)         | **NO**   | **Phase 2.7 never ran**                               |
| `logs/warnings.json`                     | **NO**   | orchestrator warnings never persisted                 |
| `logs/batch_state.json`                  | **NO**   | budget batching never invoked                         |

### 2.2 Test-file quality assessment (sampled)

| Category | Sample finding                                                                                                                                  |
|----------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| unit     | Decent. `tests/unit/middleware/auth.test.ts` mocks `jsonwebtoken`, asserts `UnauthorizedError`, uses real type signatures. **Acceptable.**      |
| api      | 29/59 files use `expect([200,403]).toContain(res.status)` — permissive contract that accepts almost anything. Same 3-pattern template per file. |
| security | 29 files share four identical patterns: `401-without-token`, `403-no-perms`, `no-stack-trace`, `SQL inject permissive 400|401|403|422`. Boilerplate.  |
| contract | Schema match assertions present but use captured-on-first-run mode without real source schemas → assert nothing meaningful.                       |
| ui/a11y  | Files written despite server skip — sub-agents should have refused (skip reason `server_unreachable_no_start_permission`).                       |

### 2.3 report-data.json shape

Actual (v1, what was written):
```json
{
  "quality_score": 88,
  "categories": { "unit": {"status":"passed","tests":47,"coverage_pct":100,"tokens":42000}, ... }
}
```

Expected (v2, what `qa_skills.report_builder` produces):
```json
{
  "version": "2.0",
  "quality_score": <real>,
  "coverage_by_category": {
    "unit": { "pct": N, "covered_items": [...], "missing_items": [...], "total": M,
              "files": [...], "stub_files": [...], "status": "...",
              "execution": { "runner": "vitest", "total": T, "passed": P, "failed": F, ... } },
    ...
  }
}
```

The v1 shape **cannot have come from `scripts/build_report.py`** — the
wrapper is schema-gated and would have exited non-zero. It was **invented by
the LLM** running `qa-coverage-reporter`, despite the `HARD GATE` instruction
in that agent's MD.

### 2.4 Symptom user observed at runtime

> "Generate all remaining security test files"
> "Generate all remaining API test files"

The orchestrator emitted batch-shortcut prompts of this form into Task calls
instead of file-level inputs. Sub-agents receiving a 47-file directive in one
shot ran out of attention and produced shallow boilerplate.

---

## 3. Root-cause classification

Four failure modes, all stemming from a single architectural choice:
**the orchestrator is itself an LLM following an MD blueprint.**

### 3.1 LLM-orchestrator skipped instructed Bash gates

The orchestrator MD (`agents/qa-orchestrator.md`, **880 lines**) instructs
the LLM to call deterministic Python wrappers at specific moments
(`agent_log.py`, `contract_diff.py`, `build_report.py`, `run_tests.py`,
`final_gate.py`, `state_write.py`, ...). When given 70 modules, 6
categories, and a budget envelope, the LLM **prioritized visible work (test
generation) and silently skipped ceremony (telemetry + verification)**.

Evidence: 0 of 6 expected `agent_output_*.json`, 0 of 6 expected
`execution_*.json`, 0 of 6 expected `domain_brief_*.json` exist.

This is not a bug. This is the **predictable failure mode** of using a
language model as the controller of a multi-phase, multi-gate pipeline. The
hard gates exist only in prose; nothing prevents skipping them.

### 3.2 Sub-agents skipped their own execution + self-validation gates

Each test-gen sub-agent MD has two `HARD GATE` sections:

1. Self-validate `AgentResult` JSON via `validate_test_output.py`.
2. Run tests via `run_tests.py` and attach `execution_result`.

Neither happened in the run. Result: sub-agents returned `status: passed`
without ever running a test, and the orchestrator (also an LLM) didn't
verify the claim.

### 3.3 Domain learning phase silently dropped

Phase 2.7 (`qa-domain-analyzer`) is the single defense against shallow
boilerplate. The orchestrator never invoked it. With no `domain_brief`,
sub-agents fell back to "generic 401 + SQL inject + no-stack-trace" four-pattern
templates that have no relation to the actual project domain.

This is **why the tests look the same across files**.

### 3.4 Batching never engaged → "Generate all remaining"

`qa_skills.budget.split_into_batches()` exists, has unit tests, is in the
MD — but the orchestrator handed 47 files to one Task call. When the
sub-agent's context filled, its prompt compressed into the literal phrase
the user saw at runtime.

`batch_state.json` is missing on disk — the loop never ran.

---

## 4. Architectural diagnosis

### 4.1 Why MD-as-program does not scale

The current architecture stacks two layers of LLM-driven orchestration:

```
test-orchestrator (skill, LLM trigger)
   └── qa-orchestrator (agent, LLM, 880-line MD)
         ├── qa-code-analyzer        (LLM, 245-line MD)
         ├── qa-env-validator        (LLM, 214-line MD)
         ├── qa-domain-analyzer × 6  (LLM, 174-line MD)
         ├── qa-{unit,api,...}-test × N batches  (LLM, 260-510-line MDs)
         ├── qa-flaky-detector       (LLM)
         └── qa-coverage-reporter    (LLM, 259-line MD)
```

Total MD payload across all agents: **3,986 lines**. The orchestrator alone
loads an 880-line MD as its system prompt, then must hold:

- `analysis.json` (70 modules, hundreds of routes)
- `RunContext`
- `path_contract.expected_files` (275 entries)
- The phase ladder (0, 0.5, 1, 1a, 1.5, 2, 2.5, 2.7, 3, 5, 6, 7, 8, 9)
- A dispatch decision matrix with server-reachability cases
- Locale rules, banner rules, abort rules
- Budget arithmetic
- A merge protocol for sub-agent telemetry

This **exceeds the working-memory budget** of the LLM in the cheap-model tier
we deliberately picked for cost. The model satisfies the obvious work (write
275 test files) and silently drops the rest.

> **Hard gates in prose are not gates. They are suggestions an LLM may decline
> for any reason and without explanation.**

### 4.2 What *is* working — the deterministic backbone

The `qa_skills` Python package is **solid**:

```
skills/_shared/qa_skills/      245 pytest tests, all green
├── path_planner.py            deterministic file layout
├── strategy.py                signal + server matrix
├── budget.py                  batch sizing + resume
├── agent_log.py               atomic per-batch persistence
├── runner.py                  vitest/jest/pytest/playwright execution
├── coverage.py                stub-aware coverage math
├── report_builder.py          v2 schema-gated assembly
├── validators.py              language-aware path regex
├── stub_markers.py            stub detection
├── server.py                  build_server_plan + reachability
├── analysis.py                load_analysis schema strip+validate
├── final_gate.py              9a/9d.2/9e disk checks
├── state.py                   carry-over state
├── quality.py                 weighted score
└── ... (artifacts, gaps, html_render, etc.)
```

And the `scripts/*.py` thin CLI wrappers map 1:1 to those modules.

**The deterministic layer is already built.** It just isn't being driven.
The LLM-orchestrator chooses whether to call it. Every failure in the run
above is a missed call to a wrapper that would have produced the correct
artifact on disk.

### 4.3 Specific architectural mismatches

| Need (project goal)                          | Current implementation                                            | Failure mode                              |
|----------------------------------------------|-------------------------------------------------------------------|-------------------------------------------|
| Wide-context domain understanding            | One LLM call to qa-domain-analyzer per category, optional         | Phase 2.7 skipped → boilerplate           |
| Deterministic phase sequencing               | LLM reads 880-line MD                                             | Phases skipped, order drift               |
| Forced execution + truthful coverage         | Wrapper exists, LLM is told "HARD GATE"                           | LLM skips Bash call                       |
| Honest report (v2 schema)                    | LLM-coverage-reporter has "HARD GATE: one Bash call"              | LLM invents v1 from memory                |
| Per-file generation (avoid context-overflow) | LLM-orchestrator instructed to batch via `budget.py`              | Skips batching, sends 47 files at once    |
| Postmortem telemetry                         | LLM-orchestrator instructed to call `agent_log.py`                | Skipped → no `agent_output_*.json`        |
| Demo-grade UX (locale, banners, polished UI) | All MD-prescribed                                                 | LLM emits banners but skips substance     |

Every cell in "Failure mode" has the same root: an LLM was asked to enforce
a contract instead of being a participant inside a contract.

---

## 5. Proposed architecture — hybrid Python driver + bounded LLM calls

### 5.1 Principle

**Move all phase sequencing, all verification, all telemetry, all report
assembly into Python.** Use LLM calls only for what an LLM is good at:

| LLM is good at (keep)                              | LLM is bad at (move to Python)                          |
|----------------------------------------------------|---------------------------------------------------------|
| Reading source files and extracting behavior       | Calling 12 wrappers in correct order                    |
| Generating idiomatic test code per file            | Computing coverage math                                 |
| Choosing meaningful assertions for one function    | Aggregating results across 6 categories                 |
| Summarizing diffs and findings                     | Enforcing schema gates on its own output                |
| Locale-aware banners                               | Deciding which file to write next                       |

### 5.2 New top-level shape

```
test-orchestrator (skill, LLM, ~50 lines)
   └── scripts/qa_run.py        Python driver. Owns the pipeline.
        │
        ├── Phase 1 — code analysis
        │     subprocess→ Task("qa-code-analyzer", {file_paths}) [LLM, scoped]
        │     verify: analysis.json on disk, schema-valid
        │
        ├── Phase 2 — strategy (pure Python)
        │     qa_skills.strategy.decide_*           [no LLM]
        │     qa_skills.path_planner.compute_*      [no LLM]
        │     qa_skills.server.build_server_plan    [no LLM]
        │
        ├── Phase 2.7 — domain learn (FORCED per category)
        │     for cat in planned:
        │         subprocess→ Task("qa-domain-analyzer", {cat, file_paths}) [LLM]
        │         verify: domain_brief_<cat>.json on disk, ≥1 behavior
        │     fail-fast if missing
        │
        ├── Phase 3 — generate (FILE-PER-TASK, never batch-as-one-prompt)
        │     for cat in planned:
        │         for batch in split_into_batches(expected_files[cat], size=3):
        │             for ef in batch:
        │                 subprocess→ Task("qa-<cat>-test",
        │                     { ONE expected_file,
        │                       ITS domain_brief slice,
        │                       prior_summary[<=5 lines] })
        │                 verify file written to ef.path
        │                 verify file passes language regex
        │                 ▶ run_tests.py CALLED BY DRIVER (not sub-agent)
        │                 ▶ agent_log.write(...) CALLED BY DRIVER
        │                 ▶ contract_diff.py CALLED BY DRIVER
        │
        ├── Phase 5 — flaky detection
        │     subprocess→ Task("qa-flaky-detector", {test_paths}) [LLM]
        │     verify flaky_detection.json
        │
        ├── Phase 6 — state_write.py [pure Python]
        ├── Phase 7 — quality.py     [pure Python]
        ├── Phase 8 — build_report.py [pure Python; ONLY way to produce report-data.json]
        ├── Phase 8b — Task("qa-html-reporter", ...) [LLM minimal, just renders]
        ├── Phase 5.5 — learnings.py [pure Python; single owner of learnings.json]
        └── Phase 9 — final_gate.py  [pure Python]
```

### 5.3 What this eliminates

| Current failure         | Why it cannot happen in new shape                                                          |
|-------------------------|--------------------------------------------------------------------------------------------|
| Phases skipped          | Driver is Python; you cannot "skip" a function call you've already written                 |
| `agent_output_*.json` missing | Driver writes it after every sub-agent return; no LLM ever chooses to call agent_log |
| Execution skipped       | Driver runs `run_tests.py` itself per-batch, before accepting the result                   |
| `domain_brief` missing  | Driver iterates categories; Phase 2.7 is a loop, not an LLM decision                       |
| v1 report shape         | `qa-coverage-reporter` agent is **deleted**; driver calls `build_report.py` directly       |
| "Generate all remaining" prompt | Sub-agent receives 1 file per Task call; physically cannot dump 47-file batch     |
| Boilerplate tests       | Sub-agent receives `domain_brief` slice + prior summary; no path to skip it                |
| Fake quality_score      | Score comes from `quality.py` only; LLM has no write path to that field                   |

### 5.4 What this preserves

- All existing `qa_skills/*.py` modules — they are correct, just unused.
- All deterministic wrappers in `scripts/*.py`.
- All `reference/*.md` test patterns (sub-agents still read them).
- The sub-agent personas (qa-unit-test, qa-api-test, ...) — but their MDs
  shrink to **~50–80 lines each**, focused on *how to write a test for the
  ONE file in this call*. No phase ladder, no Bash gates, no orchestration.
- The `test-orchestrator` skill as the user-facing trigger.
- Locale, banners, HTML polish.

### 5.5 What it adds

| New file                                       | Approx. LOC | Purpose                                  |
|-----------------------------------------------|-------------|------------------------------------------|
| `scripts/qa_run.py`                            | 350–450    | Phase-by-phase driver. Calls Task subprocess for LLM steps, calls qa_skills modules for everything else. |
| `qa_skills/driver.py`                          | 150–200    | Helpers: `task_subprocess`, `verify_on_disk`, `accept_or_retry`. |
| `qa_skills/prompt_builder.py`                  | 200–250    | Builds the **tiny** prompt JSON per sub-agent call (1 file + its slice). Replaces the bloated path_contract.expected_files=275-entry shape. |
| `tests/test_qa_run.py`                         | 150        | End-to-end driver tests with fake Task responses. |

### 5.6 What it removes / shrinks

| Item                                            | Before | After |
|-------------------------------------------------|--------|-------|
| `agents/qa-orchestrator.md`                     | 880    | ~40 lines: "invoke `scripts/qa_run.py` and surface its JSON" |
| `agents/qa-coverage-reporter.md`                | 259    | **deleted** (driver runs `build_report.py` directly) |
| `agents/qa-{unit,api,security,contract}-test.md`| ~250 each | ~80 each. No phase ladder, no gates, no orchestration. |
| `agents/qa-{ui,a11y}-test.md`                   | 281/514 | ~120 each. Server access via `server_plan` from driver, no smoke-first logic. |
| `RUNTIME_ENFORCEMENT_PLAN.md`                   | 359    | obsolete (the runtime IS the driver now) |
| `STUB_FIX_PLAN.md`                              | …      | obsolete (driver makes stubs impossible by construction) |

Net: **~2,500 lines of MD prose → ~700 lines of Python with pytest coverage**.

### 5.7 Trade-offs

| Concern                              | Impact                                                                                          |
|--------------------------------------|-------------------------------------------------------------------------------------------------|
| Loss of "LLM-as-orchestrator" demo   | True. The skill no longer showcases agentic orchestration. But the **current showcase is broken**, so this is a step toward something demoable rather than away from it. We still showcase 7 LLM sub-agents — just bounded ones. |
| File-per-Task → more LLM calls       | Yes. 275 files × ~1k input tokens each ≈ 275k token cost vs. 6 large bloated calls. But the bloated calls produce trash, and per-file calls let us **cache** the domain_brief once per cat. Net cost likely lower per *real* test. |
| Python driver requires Python on user machine | Already required — every wrapper is Python. No new dependency.                          |
| Less "magic" — more code             | Yes. That's the goal. The magic was hiding the failure.                                          |
| Migration effort                     | ~2 days of focused work for driver + sub-agent MD shrink + retest.                              |

---

## 6. Migration plan (concrete)

Phased so each step ships green pytest before the next starts.

### Step A — Driver skeleton + Phase 1/2 (no LLM-orchestrator yet)

1. Write `scripts/qa_run.py` covering Phase 0, 1, 2 (analyzer + strategy +
   path planner). Reuse existing wrappers.
2. Write `qa_skills/driver.py` with `task_subprocess()` returning the
   sub-agent JSON and `verify_on_disk(path)`.
3. New pytest: end-to-end with `Task` mocked → confirms `analysis.json`,
   `strategy.json`, `expected_files.json` produced.

### Step B — Phase 2.7 forced loop

1. Driver iterates `planned_categories`, calls `qa-domain-analyzer` per cat
   with `{file_paths, expected_files_slice}`.
2. Driver **rejects** sub-agent output if `domain_brief_<cat>.json` is
   missing on disk OR has zero behaviors. Retry once with explicit prompt
   suffix; then fail-soft `domain_brief_unavailable:<cat>` warning.
3. Pytest with stubbed Task: verifies the driver writes
   `domain_brief_*.json` for every planned cat OR records the warning.

### Step C — Phase 3 file-per-Task dispatch

1. Driver loops categories → batches (`qa_skills.budget`) → files.
2. Per file: build tiny prompt JSON (1 expected_file + 1 domain_brief entry
   + prior_summary), `Task(agent, prompt)`, verify file on disk, run
   `validate_test_output.py`, run `run_tests.py`, write `agent_log.py`.
3. **Sub-agent MD shrink** — replace each `agents/qa-*-test.md` with a
   ~80-line focused MD that takes a single-file input. Strip every "phase",
   "gate", "self-validate" section.
4. Pytest with stubbed Task returning canned `tests_passing` data: verifies
   `agent_output_<agent>.json`, `execution_<agent>.json`,
   `batch_state.json` all on disk; verifies prompt size is bounded.

### Step D — Phases 5/6/7/8/9 = pure Python

1. `state_write.py`, `quality.py`, `build_report.py`, `final_gate.py` —
   already exist. Driver just calls them.
2. **Delete** `agents/qa-coverage-reporter.md`. Update README.
3. Phase 8b: driver invokes `Task("qa-html-reporter")` with already-built
   `report-data.json`. Reporter only renders.

### Step E — Cutover

1. Rewrite `agents/qa-orchestrator.md` to be a 40-line trigger that runs
   `scripts/qa_run.py` and returns its stdout.
2. Update `skills/test-orchestrator/SKILL.md` if needed (probably no change).
3. Re-run on Candidate_Mngmnt. Verify:
   - `report-data.json` v2 schema
   - all 6 `execution_*.json` exist with real test runs
   - all 6 `domain_brief_*.json` exist with behaviors
   - `agent_output_*.json` exist per agent
   - tests look domain-driven (no "Generate all remaining" boilerplate)
   - `quality_score` reflects real coverage + real failures

### Step F — Cleanup

1. Delete `RUNTIME_ENFORCEMENT_PLAN.md`, `STUB_FIX_PLAN.md` (superseded).
2. Add `ARCHITECTURE.md` (this document, post-cutover, condensed).
3. Add `CHANGELOG.md` entry: v2.0 — Python-driven pipeline.

---

## 7. Risks & mitigations

| Risk                                                                | Mitigation                                                                                       |
|---------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| Task subprocess interface unstable                                  | Mock-tested. If Anthropic changes Task semantics, only `driver.task_subprocess()` needs to change. |
| Per-file LLM calls cost more in tokens                              | Cache domain_brief per cat. Skip files with no behaviors in brief. Expected ≤ 1.5× current spend on a project that actually finishes.|
| Long-running runs (275 files × few seconds per LLM call)            | Already exists. `batch_state.json` checkpointing lets resume. Parallelize within a window of 3 (`budget.MAX_PARALLEL_BATCHES_PER_CATEGORY`). |
| Sub-agent prompts still too long                                    | Driver controls prompt → bounded by construction. Cap at 4k tokens input per call.                |
| User loses agentic-demo angle                                       | Re-frame demo: "Python driver coordinates 7 specialist LLM agents, each with bounded scope." That's still a strong story and it actually works. |

---

## 8. Recommendation

**Adopt the hybrid Python-driver architecture (§5).**

The deterministic backbone is already built (245 green pytest); the failing
piece is the LLM-orchestrator on top of it. Replacing that layer with a
Python driver:

- Eliminates every failure mode observed in the Candidate_Mngmnt run.
- Reduces MD prose by ~2,500 lines.
- Adds ~700 lines of Python with pytest coverage.
- Preserves the LLM strengths (per-file code generation, domain extraction).
- Makes the system honest by construction: no path exists to fake green.

The current architecture cannot be patched into reliability. Adding more
`HARD GATE` text to the orchestrator MD is treating the symptom — the LLM
is the wrong layer to enforce gates on itself.

---

## 9. What to do next (one decision)

Approve §5–§6 and I will execute Steps A–F. Estimated effort: 2 working days
of focused implementation, ending with a re-run on Candidate_Mngmnt that
produces a v2 report-data with real execution numbers and domain-driven
tests.

If you want a smaller bite first, Step A + Step B alone are enough to prove
the driver pattern works and demonstrate that domain_brief generation
becomes mandatory under driver control.
