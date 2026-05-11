# STUB_FIX_PLAN — Eliminate Silent Stub Fallback

> Status: PROPOSED — not yet executed
> Trigger: Real-world run on `Candidate_Mngmnt` produced 541 stub files / 26 real (95% failure rate, silently reported as `quality_score: 50`).
> Goal: Make stubs IMPOSSIBLE. Failures must be visible; coverage must reflect reality.

## Diagnosis recap

| Symptom (Candidate_Mngmnt run) | Count |
|---|---|
| Files emitted total | 567 |
| Stub files (`Auto-generated stub` signature) | 541 (95%) |
| Real LLM-generated files | 26 (5%) |
| Real files at WRONG path (`test_X.ts` instead of `X.test.ts`) | 10 |
| UI files (all stubs) | 48/48 (100%) |
| a11y files (all stubs) | 48/48 (100%) |
| Quality score reported | 50/100 (misleading — based on file count, not content) |

## Root causes (the five gaps)

1. **Budget arithmetic absent** — sub-agents dispatched 100+ files within 600s budget; ~15-20 fit. Remainder filled by silent stub fallback.
2. **Naming convention not language-aware** — `path_regex` accepts both `test_X.ts` and `X.test.ts`. TS sub-agent emitted Python prefix; expected_files contract demanded TS form; orchestrator filled correct path with stub, sub-agent's real file orphaned alongside.
3. **`server_plan` matrix bypassed at dispatch** — UI/a11y dispatched despite `start_allowed=false, start_command=null, unreachable`. Sub-agents produced stubs because they could not reach the server.
4. **Stub-content detection missing in Phase 9** — final-gate checks file *existence*, not content. Stubs pass.
5. **Contract-violation tolerated** — sub-agent emitting paths outside `expected_files` should reject the entire AgentResult. Today orchestrator silently fills missing slots with stubs.

## Architecture principle (NEW)

**Stubs are bugs.** No code path may emit a placeholder file under `tests/`. Missing test = `missing_items[]` entry in coverage. Honest gap reporting is better than fake green.

---

## Track A — Critical fixes (must land first)

### A1. Stub-content detection in `final_gate`

**File:** [skills/_shared/qa_skills/final_gate.py](skills/_shared/qa_skills/final_gate.py)

**Change:** Add new check `9f` (between 9d.2 and 9e).

```python
STUB_MARKERS = (
    "Auto-generated stub",
    "Auto-generated stub.",
    "placeholder — add",
    "TODO: import and test",
    "TODO: Use axe-playwright",
    "TODO: Navigate to the component",
    "// Placeholder — enhance",
    "expect(true).toBe(true)",       # vitest/jest placeholder body
    "assert True  # placeholder",    # pytest placeholder body
)

def check_stub_content(project_root: Path, report_data: dict) -> list[str]:
    warnings = []
    for cat, info in report_data["coverage_by_category"].items():
        for fpath in info.get("files", []):
            full = project_root / fpath
            if not full.is_file():
                continue
            content = full.read_text(encoding="utf-8", errors="ignore")
            if any(m in content for m in STUB_MARKERS):
                warnings.append(f"stub_content:{cat}:{fpath}")
    return warnings
```

**Result:** If ≥1 file is a stub → `final_status = partial`, warning list grows. User sees count + paths in final summary banner.

**Acceptance pytest** ([test_final_gate.py](skills/_shared/qa_skills/tests/test_final_gate.py)):
- Stub file present → warning emitted.
- Real file (no marker) → no warning.
- Empty `files[]` → no warning.

### A2. Kill stub fallback in orchestrator dispatch

**File:** [agents/qa-orchestrator.md](agents/qa-orchestrator.md) — Phase 3.

**Change:** Remove every "fill missing expected_files with stub" path. After each Task call:

```python
# Phase 3 post-dispatch
agent_out = task_result
emitted_paths = {o["path"] for o in agent_out.get("outputs", []) if validate_path(o["path"])[0]}
expected_set  = {ef["path"] for ef in agent_input["path_contract"]["expected_files"]}

extras  = emitted_paths - expected_set      # wrong-named files (e.g. test_X.ts on TS)
missing = expected_set - emitted_paths      # never generated

# Hard policy: no fallback writes. Missing stays missing.
for p in extras:
    Path(project_root / p).unlink(missing_ok=True)      # delete sub-agent's wrong path
    warnings.append(f"path_contract_violation:{p}")

if missing:
    agent_out["status"] = "partial"
    agent_out["missing_items"] = sorted(missing)
    warnings.append(f"agent_unmet_contract:{agent_out['agent']}:{len(missing)}_files")

# NEVER:
#   write_stub(p) for p in missing
#   write_placeholder(p)
#   scaffold(p)
```

**Result:** Missing files show up in `coverage[cat].missing_items[]`, not as stubs.

### A3. `server_plan` matrix enforcement before dispatch

**File:** [agents/qa-orchestrator.md](agents/qa-orchestrator.md) — Phase 2.5 build_plan section.

**Change:** Before adding `ui` or `a11y` to `categories_planned`, run:

```python
plan = build_server_plan(analysis, mode, allow_start_explicit)
reachable = is_reachable(plan.url) if plan.url else False

if cat in ("ui", "a11y") and not reachable:
    if not plan.start_allowed or not plan.start_command:
        # honor matrix — skip, do not dispatch
        categories_skipped.append({
            "name": cat,
            "reason": "server_unreachable_no_start_permission"
                     if not plan.start_allowed
                     else "server_unreachable_no_start_command",
        })
        continue   # never dispatched
    # else: orchestrator spawns start_command, polls, then dispatches
```

**Move** this gate from Phase 3 (where it currently lives in the dispatch decision matrix table) into Phase 2.5 strategy build. The strategy plan must reflect reality BEFORE dispatch.

**Acceptance pytest** ([test_strategy.py](skills/_shared/qa_skills/tests/test_strategy.py)):
- `server_plan.url=None` + ui category → `should_run=false, reason=server_unreachable_no_start_permission`.
- `start_command=null, !start_allowed` → skip ui+a11y.
- Reachable + ui → dispatch.

### A4. Language-aware path regex

**File:** [skills/_shared/qa_skills/validators.py](skills/_shared/qa_skills/validators.py)

**Change:** Split single `PATH_REGEX` into per-language variants. Reject mismatches at sub-agent self-validation.

```python
# Python projects only — file MUST start with `test_` prefix, MUST end `.py`
PY_PATH_REGEX = re.compile(
    r"^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+test_[^/]+\.py$"
)

# TS/JS projects only — file MUST end with `.spec.ts(x)?|.test.ts(x)?|.api.test.ts|...`
# MUST NOT start with `test_` (that is Python convention).
TS_PATH_REGEX = re.compile(
    r"^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+"
    r"(?!test_)"                                # negative lookahead: reject test_ prefix
    r"[^/]+\.(spec|test|api\.test|security\.test|contract\.test|a11y\.spec)\.(ts|tsx|js|jsx)$"
)

def validate_path(path: str, language: str) -> tuple[bool, str]:
    regex = PY_PATH_REGEX if language == "python" else TS_PATH_REGEX
    if regex.match(path):
        return True, ""
    return False, f"path_regex_violation_{language}:{path}"
```

**Migration:**
- `validate_test_output(result, language)` — add `language` arg, plumb through wrapper.
- `path_contract.required_pattern` — emit the language-correct regex per project.
- Sub-agents self-validate before Write (existing Phase 6 in each test-gen agent).

**Acceptance pytest** ([test_validators.py](skills/_shared/qa_skills/tests/test_validators.py)):
- TS project + `tests/api/auth/test_login.api.test.ts` → REJECTED with `path_regex_violation_typescript`.
- TS project + `tests/api/auth/login.api.test.ts` → accepted.
- Python project + `tests/api/auth/test_login.py` → accepted.
- Python project + `tests/api/auth/login.test.py` → REJECTED.

### A5. Budget-aware dispatch with batch + partial

**File:** [agents/qa-orchestrator.md](agents/qa-orchestrator.md) — Phase 3 dispatch + new helper `qa_skills.budget`.

**New module:** [skills/_shared/qa_skills/budget.py](skills/_shared/qa_skills/budget.py)

```python
"""Budget arithmetic for sub-agent dispatch.

Each generated test file costs ~30-60s LLM time. Orchestrator must batch when
expected_files.count exceeds what fits in per_agent_timeout_seconds.
"""

AVG_SECONDS_PER_FILE = 45      # empirical; adjust after telemetry
SAFETY_FACTOR        = 0.7     # account for fix-iterations + I/O

def estimate_fit(files_count: int, timeout_seconds: int) -> tuple[int, int]:
    """Return (fits, batch_count)."""
    fits_per_batch = max(1, int(timeout_seconds * SAFETY_FACTOR / AVG_SECONDS_PER_FILE))
    batch_count    = (files_count + fits_per_batch - 1) // fits_per_batch
    return fits_per_batch, batch_count

def split_into_batches(expected_files: list, fits_per_batch: int) -> list[list]:
    return [expected_files[i:i+fits_per_batch] for i in range(0, len(expected_files), fits_per_batch)]
```

**Orchestrator Phase 3 change:**

```python
for cat, agent_name in planned_categories:
    expected = expected_files_by_cat[cat]
    fits, n_batches = estimate_fit(len(expected), budgets["per_agent_timeout_seconds"])

    if n_batches == 1:
        # single dispatch
        result = Task(agent_name, build_input(expected))
    else:
        # batched dispatch — each batch is its own Task call
        merged_outputs = []
        for batch in split_into_batches(expected, fits):
            r = Task(agent_name, build_input(batch))
            if r["status"] == "error":
                # abort remaining batches; mark partial
                merged_outputs.extend(r.get("outputs", []))
                break
            merged_outputs.extend(r.get("outputs", []))
        result = aggregate(merged_outputs, agent_name)

    # No fallback writes. If status != passed → reflected in coverage as missing_items.
```

**Acceptance pytest** ([test_budget.py](skills/_shared/qa_skills/tests/test_budget.py)):
- 100 files, 600s timeout → fits=9, batches=12.
- 5 files, 600s → fits=9, batches=1.
- Edge: 0 files → batches=0.

### A5.b Parallel batches + resume (scale to hundreds)

**Motivation:** A5 alone produces sequential batches. 100 files × 6 categories = 72 Task calls serial → ~9h wall-time. Plus single run failure loses all progress.

**File:** [skills/_shared/qa_skills/budget.py](skills/_shared/qa_skills/budget.py) (extend) + [agents/qa-orchestrator.md](agents/qa-orchestrator.md) Phase 3.

**Generic, no project-specific code.**

```python
# qa_skills/budget.py — additions
import json
from pathlib import Path

MAX_PARALLEL_BATCHES_PER_CATEGORY = 3   # tunable; respects rate limits

def batch_state_path(logs_dir: Path) -> Path:
    return logs_dir / "batch_state.json"

def load_batch_state(logs_dir: Path) -> dict:
    p = batch_state_path(logs_dir)
    if not p.is_file():
        return {}
    return json.loads(p.read_text())

def save_batch_state(logs_dir: Path, state: dict) -> None:
    batch_state_path(logs_dir).write_text(json.dumps(state, indent=2))

def batch_id(category: str, idx: int) -> str:
    return f"{category}:{idx:03d}"

def is_completed(state: dict, bid: str) -> bool:
    return state.get(bid, {}).get("status") == "completed"

def mark_completed(state: dict, bid: str, output_paths: list[str]) -> None:
    state[bid] = {"status": "completed", "outputs": output_paths}

def summarize_prior_batches(state: dict, category: str) -> list[dict]:
    """Compact prior-batch summary for context-warm dispatch.

    Returns list of {batch_id, paths[]} — NO code content, just paths.
    Keeps sub-agent aware of sibling work without exploding context.
    """
    out = []
    for bid, info in state.items():
        if bid.startswith(f"{category}:") and info.get("status") == "completed":
            out.append({"batch_id": bid, "paths": info.get("outputs", [])})
    return out
```

**Orchestrator Phase 3 change (replaces sequential loop from A5):**

```python
# Per category — parallel dispatch with resume + prior-batch awareness
state = load_batch_state(logs_dir)

for cat, agent_name in planned_categories:
    expected = expected_files_by_cat[cat]
    fits, n_batches = estimate_fit(len(expected), budgets["per_agent_timeout_seconds"])
    batches = split_into_batches(expected, fits)

    pending_batches = [
        (i, b) for i, b in enumerate(batches)
        if not is_completed(state, batch_id(cat, i))
    ]

    # Parallel dispatch within a window — respects MAX_PARALLEL_BATCHES_PER_CATEGORY
    for window in chunked(pending_batches, MAX_PARALLEL_BATCHES_PER_CATEGORY):
        prior = summarize_prior_batches(state, cat)
        in_flight = []
        for idx, batch in window:
            agent_input = build_input(
                batch,
                prior_batches_summary=prior,   # context-warm: paths only, no code
            )
            in_flight.append(
                (idx, Task(agent_name, agent_input, run_in_background=True))
            )
        for idx, task_handle in in_flight:
            r = await_task(task_handle)
            output_paths = [o["path"] for o in r.get("outputs", [])]
            mark_completed(state, batch_id(cat, idx), output_paths)
            save_batch_state(logs_dir, state)    # persist after each batch
```

**Sub-agent input contract addition:**

`agent_input["prior_batches_summary"]: list[{batch_id, paths[]}]` — generic field. Sub-agent reads it (when present) to avoid duplicating helpers already covered. NO code content shared, only paths.

**Tuning constants (generic, declared empirical):**
```python
AVG_SECONDS_PER_FILE              = 45     # empirical, project-agnostic
SAFETY_FACTOR                     = 0.7
MAX_PARALLEL_BATCHES_PER_CATEGORY = 3      # rate-limit safe default
```

**Acceptance pytest** ([test_budget.py](skills/_shared/qa_skills/tests/test_budget.py)):
- `load_batch_state` returns `{}` when no file exists.
- `mark_completed` + `save_batch_state` round-trip preserves data.
- `is_completed` returns False for missing batch_id, True after `mark_completed`.
- `summarize_prior_batches(state, "unit")` returns only `unit:*` completed entries.
- `batch_id("api", 12) == "api:012"`.
- Resume scenario: state with 5/12 completed → `pending_batches` returns indices 5..11.

**Scale acceptance (manual run, post-fix):**
- 100 expected_files in `api` category → 12 batches → 4 parallel windows × 3 batches → ~3× wall-time speedup vs serial.
- Kill orchestrator mid-run at batch 7 → restart → resume from batch 7 (1-6 marked completed in state).

---

## Track B — Hardening (after Track A lands)

### B1. AgentResult extras-and-violations reporter

**File:** [skills/_shared/qa_skills/validators.py](skills/_shared/qa_skills/validators.py)

```python
def validate_agent_result_against_contract(
    result: dict,
    expected_files: list[dict],
    language: str,
) -> dict:
    """Return {extras: [...], missing: [...], violations: [...]}."""
    expected = {ef["path"] for ef in expected_files}
    emitted  = {o["path"] for o in result.get("outputs", [])}
    extras   = sorted(emitted - expected)
    missing  = sorted(expected - emitted)

    violations = []
    for p in emitted:
        ok, err = validate_path(p, language)
        if not ok:
            violations.append(err)

    return {"extras": extras, "missing": missing, "violations": violations}
```

**Orchestrator wires this in Phase 3 post-dispatch** (replacing the inline diff in A2).

### B2. Coverage truth: stub-aware `compute_coverage`

**File:** [skills/_shared/qa_skills/coverage.py](skills/_shared/qa_skills/coverage.py)

`compute_coverage` already uses `outputs[].covers` ∩ universe. Add: a file path counted in coverage MUST also pass stub-content check.

```python
def is_real_test(content: str) -> bool:
    return not any(m in content for m in STUB_MARKERS)

# inside compute_coverage:
real_outputs = [o for o in outputs if is_real_test(read(project_root / o["path"]))]
# universe ∩ real_outputs.covers
```

**Catch:** requires `project_root` parameter (not currently passed). Plumb through.

**Acceptance pytest:** stub file with valid `covers[]` does NOT count toward coverage.

### B3. Auto-installed quality check in HTML report

**File:** [skills/_shared/qa_skills/html_render.py](skills/_shared/qa_skills/html_render.py)

When `warnings[]` contains `stub_content:` or `agent_unmet_contract:` entries:
- Red banner at top of report: "⚠️ N files are stubs — quality_score is unreliable."
- Stub files listed in a collapsible `<details>` per category.

### B4. Telemetry: log every AgentResult to disk

**File:** [agents/qa-orchestrator.md](agents/qa-orchestrator.md) — Phase 3 post-dispatch.

```bash
echo "$AGENT_RESULT_JSON" > "${LOGS_DIR}/agent_output_${agent_name}.json"
```

Currently `.qa-skills/logs/<run>/` has only `analysis.json`, `expected_files.json`, `strategy.json`. After this fix: also `agent_output_qa-unit-test.json` etc. for postmortem.

---

## Track C — Cleanup (optional, after A+B prove out)

### C1. Drop `path_contract.required_pattern` from input — derive from language

Today every sub-agent receives `required_pattern` in path_contract. After A4 this is redundant: language-aware regex lives in validators.

### C2. Unify stub markers in single module

Single source of truth: `qa_skills.stub_markers.STUB_MARKERS` tuple. Imported by `final_gate`, `coverage`, `html_render`.

### C3. Update REFACTOR_PLAN.md status

Mark this plan complete when Tracks A+B land.

---

## Acceptance: Candidate_Mngmnt re-run

After A+B implemented, re-running on Candidate_Mngmnt MUST produce:

| Metric | Before fix | After fix (expected) |
|--------|------------|----------------------|
| Stub files | 541 (95%) | **0** |
| Real files | 26 (5%) | ≤ what fits in budget (e.g. 60-100) |
| Missing files | 0 (hidden as stubs) | **541** visible in `coverage[cat].missing_items` |
| UI/a11y status | `passed` (lie) | `skipped:server_unreachable_no_start_permission` |
| Wrong-path files (`test_X.ts` on TS) | 10 (orphaned) | **0** (rejected by language-aware regex; sub-agent retries or marks `path_regex_violation`) |
| Quality score | 50 (misleading) | <30 (honest — most categories partial/skipped) |
| User-visible signal | None ("✅ Done.") | "⚠️ N stubs detected. M missing. K path violations." |

---

## Execution order

1. **A4** (language-aware regex) — smallest, foundational. Tests in isolation.
2. **A1** (stub detection in final_gate) — independent, immediate user-visible benefit.
3. **A3** (server_plan enforcement at strategy phase) — purely orchestrator + strategy. Mostly .md edit + 1 pytest.
4. **A5** (budget arithmetic + batching) — new module + orchestrator dispatch rewrite.
5. **A5.b** (parallel batches + resume) — scale enabler; layered on A5.
6. **A2** (kill stub fallback) — orchestrator change. Depends on A5 to make batching the real fix.
7. **B1, B2, B3, B4** — additive once A is green.

## Risk

- **A2 + A5** mean Candidate_Mngmnt's next run will show LOWER coverage. User sees honest reality for first time. This is the point — but expect "regression" complaints unless framed properly in HTML report banner (B3).
- **A4** breaks any project that has Python-style names on TS — none in our test fixtures, but a real-world TS project might have pre-existing `test_foo.ts` files. Mitigation: regex only enforced for NEWLY emitted paths from sub-agents in this run. Existing files untouched.

## Estimated effort

| Track | Module changes | MD changes | Pytest | Total LOC |
|-------|----------------|------------|--------|-----------|
| A1 | +30 final_gate.py | 0 | +60 | ~90 |
| A2 | 0 | +50 orchestrator.md | 0 | ~50 |
| A3 | +20 strategy.py | +30 orchestrator.md | +40 | ~90 |
| A4 | +30 validators.py, +5 each test-gen agent script | +20 each sub-agent (×6) | +80 | ~250 |
| A5 | +60 new budget.py | +80 orchestrator.md | +50 | ~190 |
| A5.b | +60 budget.py (resume+parallel) | +40 orchestrator.md | +50 | ~150 |
| B1-B4 | +80 across modules | +30 across agents | +60 | ~170 |
| **Total** | **~285 module LOC** | **~250 .md LOC** | **~340 pytest LOC** | **~990 LOC** |

Plan ends.
