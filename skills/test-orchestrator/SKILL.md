---
name: test-orchestrator
description: >
  Central QA orchestrator — automatically generates, runs, and reports a full test suite
  for any codebase. This is the SINGLE ENTRY POINT for all QA activities in this project.
  Trigger this skill for any test-related request, regardless of how the user phrases it.

  English triggers: "generate tests", "write tests", "write tests for", "run tests",
  "test my code", "what's my test coverage", "what am I missing in tests", "update tests",
  "scan my code for tests", "check test quality", "test coverage analysis", "create tests",
  "build test suite", "I need tests", "check what's untested".

  Hebrew triggers (טריגרים בעברית): "צור בדיקות", "כתוב בדיקות", "הרץ בדיקות",
  "בנה בדיקות", "יצירת בדיקות", "מה הכיסוי שלי", "מה לא נבדק", "עדכן בדיקות",
  "סרוק את הקוד לבדיקות", "בדוק את הפרויקט שלי", "ניתוח כיסוי בדיקות",
  "אני רוצה בדיקות", "צריך בדיקות", "תייצר בדיקות", "תכתוב בדיקות",
  "תרוץ בדיקות", "מה לא נבדק בקוד".

  Requires only: project path. Handles everything else automatically.
  Output: HTML report that opens in the browser.
---

# test-orchestrator

Central coordinator for the QA skills system. Scans the codebase, decides what to test,
dispatches test generation to sub-skills, runs tests, fixes failures, runs flaky detection,
and produces an HTML report.

---

## RUN COMPLETION CONTRACT

Every run MUST produce ALL FOUR of these artifacts before being considered complete:

1. `{project_root}/test-state.json`
2. `{project_root}/test-reports/report-data.json`
3. `{project_root}/test-reports/report-{name}-{YYYYMMDD-HHMM}.html`
4. `{project_root}/.qa-skills/checkpoints/run.json` with `"completed": true`

**If any artifact is missing, the run is INCOMPLETE — regardless of whether tests passed.**
Do NOT display the success summary until all four exist on disk.

---

## Communication style

Detect the user's language from their message and respond accordingly.
Keep all status messages simple and non-technical — the audience is manual QA testers, not developers.

**Hebrew messages:**
```
סורק את הפרויקט ב-{path}...
נמצאו {N} קבצים | {language} | {capabilities}
בודק שינויים מהריצה הקודמת...
{N} קבצים השתנו | {M} קבצים חדשים | {K} ללא שינוי
מייצר בדיקות...
מריץ בדיקות ובודק תוצאות...
✅ הושלם. {N} בדיקות חדשות | {M} עודכנו | {K} ללא שינוי
📄 הדוח נפתח בדפדפן: {path}
```

**English messages:**
```
Scanning {path}...
Found {N} files | {language} | {capabilities}
Checking for changes since last run...
{N} files changed | {M} new | {K} unchanged
Generating tests...
Running tests and checking results...
✅ Done. {N} new tests | {M} updated | {K} unchanged
📄 Report opened in browser: {path}
```

---

## Sub-skills location

This orchestrator delegates to the following sub-skills. When instructed to invoke a sub-skill,
read its SKILL.md file and follow its instructions.

All skills install to `~/.claude/skills/`. Read from there:

```
~/.claude/skills/code-analyzer/SKILL.md
~/.claude/skills/git-diff-analyzer/SKILL.md
~/.claude/skills/env-validator/SKILL.md
~/.claude/skills/unit-test/SKILL.md
~/.claude/skills/api-test/SKILL.md
~/.claude/skills/security-test/SKILL.md
~/.claude/skills/ui-playwright/SKILL.md
~/.claude/skills/accessibility-test/SKILL.md
~/.claude/skills/contract-test/SKILL.md
~/.claude/skills/flaky-detector/SKILL.md
~/.claude/skills/coverage-reporter/SKILL.md
~/.claude/skills/html-reporter/SKILL.md
```

If `~/.claude/skills/` is not found (non-standard install), locate the skill directory by running:
```bash
find ~ -name "code-analyzer" -path "*/skills/*" -type d 2>/dev/null | head -1 | xargs dirname
```

---

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_path` | Yes | Absolute path to the project root |
| `force_full` | No | If `true`, ignore state and regenerate all tests |
| `categories` | No | Limit to specific skills: `["unit", "api", "ui", "security"]` |

Ask the user for `project_path` if not provided. Do not assume CWD.

---

## RunContext construction

Before Phase 0 begins, build the shared `RunContext` object and pass it to every sub-skill:

```python
import uuid, os, datetime

run_id = str(uuid.uuid4())
checkpoint_dir = os.path.join(project_path, ".qa-skills", "checkpoints")
logs_dir = os.path.join(project_path, ".qa-skills", "logs", run_id)

context = {
    "run_id": run_id,
    "project_root": project_path,
    "language": None,         # filled after Phase 1
    "additional_languages": [],
    "analysis": None,         # filled after Phase 1
    "changed_modules": [],    # filled after Phase 2
    "all_test_outputs": [],   # filled after Phase 3
    "execution_results": {},  # filled after Phase 4
    "flaky_tests": [],        # filled after Phase 5
    "quality_score": 0,       # filled after Phase 7
    "user_locale": detect_locale(user_message),   # "he" or "en"
    "categories_enabled": categories or ["unit", "api", "ui", "security", "a11y", "contract"],
    "checkpoint_dir": checkpoint_dir,
    "logs_dir": logs_dir,
    "budget": {"max_seconds_per_skill": 600, "max_tests_per_module": 30}
}
```

`detect_locale`: if user's message contains Hebrew characters → "he", else "en".

---

## Resume check (before Phase 0)

```python
checkpoint_path = os.path.join(checkpoint_dir, "run.json")
if os.path.exists(checkpoint_path):
    with open(checkpoint_path) as f:
        prior = json.load(f)
    age_hours = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(
                 prior["updated_at"].rstrip("Z"))).total_seconds() / 3600
    if age_hours < 24 and not prior.get("completed"):
        ask_user = get_message("resume_prompt", locale, phase=prior["phase_name"])
        # If user confirms: restore context from prior, skip completed phases
        # If user declines: proceed fresh
```

Write checkpoint after each phase:
```python
def write_checkpoint(phase: int, phase_name: str, completed_skills: list):
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    with open(checkpoint_path, "w") as f:
        json.dump({
            "run_id": run_id,
            "phase": phase,
            "phase_name": phase_name,
            "completed_skills": completed_skills,
            "started_at": run_start_iso,
            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "completed": False
        }, f, indent=2)
```

---

## Phase 0 — Setup

**This phase is MANDATORY. Do not proceed to Phase 1 if it fails.**

```python
import os

os.makedirs(checkpoint_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

# Verify directories were created
assert os.path.isdir(checkpoint_dir), f"FATAL: cannot create {checkpoint_dir}"
assert os.path.isdir(logs_dir),       f"FATAL: cannot create {logs_dir}"
```

Write initial checkpoint:
```python
write_checkpoint(0, "setup", [])
```

**Postcondition:** `{project_root}/.qa-skills/checkpoints/` and `{project_root}/.qa-skills/logs/{run_id}/` both exist on disk.
If either is missing, abort with a clear error message. Do not proceed silently.

---

## Phase 1 — Scan

**Read `~/.claude/skills/code-analyzer/SKILL.md` and follow its instructions on `project_path`.**

Capture full JSON output as `analysis`. Update `context["analysis"]` and `context["language"]`.

Display to user:
```
scan_start → scan_done → capabilities_found
```

After scan, **invoke `git-diff-analyzer`**:
Read `~/.claude/skills/git-diff-analyzer/SKILL.md`, pass context, get back updated `analysis.modules` with `diff_class` added.

**Then invoke `env-validator`**:
Read `~/.claude/skills/env-validator/SKILL.md`, pass context.
Replace `context["categories_enabled"]` with `env_report["categories_remaining"]`.

Write checkpoint: `write_checkpoint(1, "scan", ["code-analyzer", "git-diff-analyzer", "env-validator"])`.

**Postcondition:** `context["analysis"]` is not None AND `context["analysis"]["modules"]` is a non-empty list.
If postcondition fails, abort — cannot proceed without analysis.

---

## Phase 2 — State check

Look for `{project_path}/test-state.json`.

**If file exists and `force_full` is not true:**
```python
import json, hashlib

with open("test-state.json") as f:
    state = json.load(f)

changed_modules = []
for module in analysis["modules"]:
    saved = state["modules"].get(module["path"])
    if not saved or saved["hash"] != module["hash"]:
        changed_modules.append(module)

new_modules = [m for m in analysis["modules"]
               if m["path"] not in state["modules"]]
```

Apply `diff_class` filter on top of hash check:
```python
for m in list(changed_modules):
    dc = m.get("diff_class", "unknown")
    if dc == "trivial":
        changed_modules.remove(m)
        # Log: "Trivial change in {path} — skipping test update"
```

If `changed_modules + new_modules` is empty:
→ Tell user (using message key `state_no_change`)
→ Still run Phase 7 (coverage) and Phase 8 (report) with existing data.
→ Skip Phases 3–6. Jump directly to Phase 7.

**If no state file:**
- `changed_modules` = all modules in `analysis["modules"]`
- Display using `state_no_prior` message key.

**`run_type`** = `"incremental"` if state existed, `"full"` otherwise.

Update context: `context["changed_modules"] = changed_modules`.
Write checkpoint: `write_checkpoint(2, "state_check", [])`.

**Postcondition:** `context["changed_modules"]` is set (may be empty list).

---

## Phase 3 — Dispatch (test generation)

Based on `analysis` and `changed_modules`, decide which skills to invoke.

### Decision matrix

| Condition | Skill |
|-----------|-------|
| Always | `unit-test` |
| `analysis.stats.has_frontend == true` AND changed modules include frontend files | `ui-playwright` |
| `analysis.routes` non-empty AND changed modules include controller/route files | `api-test` |
| Any changed module has `has_auth: true` OR `has_db_queries: true` OR non-empty `input_fields` | `security-test` |
| `a11y` in `categories_enabled` AND `has_frontend` | `accessibility-test` |
| `contract` in `categories_enabled` AND routes non-empty | `contract-test` |

Override: if `categories` parameter provided, only dispatch listed categories.

### How to invoke each skill

For each skill to invoke, **read its SKILL.md from `~/.claude/skills/<skill-name>/SKILL.md`**
and follow its instructions. Pass the full `RunContext`.

Run `unit-test`, `ui-playwright`, `api-test`, `security-test`, `accessibility-test`, `contract-test`
**in parallel** when all inputs are ready.

### Failure isolation

```python
def invoke_skill_safe(skill_name: str, context: dict) -> list:
    try:
        result = invoke_skill(skill_name, context)
        ok, errors = validate_or_warn(result, "test_output")
        if not ok:
            log_warn(f"skill_invalid_output: {skill_name}: {errors}")
            return [{"source_module": "unknown", "path": "", "tests_written": 0,
                     "assertions_covered": [],
                     "status": "error", "error_message": f"Invalid output: {errors}"}]
        return result
    except TimeoutError:
        return [{"source_module": "unknown", "path": "", "tests_written": 0,
                 "assertions_covered": [],
                 "status": "partial", "error_message": "timeout"}]
    except Exception as e:
        return [{"source_module": "unknown", "path": "", "tests_written": 0,
                 "assertions_covered": [],
                 "status": "error", "error_message": str(e)}]
```

All skills run regardless of individual failures. Never abort the full run.

### Deduplication

```python
seen_assertions = set()
for output_list in all_test_outputs:
    for item in output_list:
        filtered = [a for a in item.get("assertions_covered", [])
                    if a not in seen_assertions]
        seen_assertions.update(item.get("assertions_covered", []))
        item["assertions_covered"] = filtered
```

Store results: `context["all_test_outputs"] = all_test_outputs`.

Write checkpoint: `write_checkpoint(3, "dispatch", skills_invoked)`.

**Postcondition:** `context["all_test_outputs"]` is a non-empty list. Each item has at minimum
`source_module`, `path`, `tests_written`, `status`. If all skills returned errors, still proceed
— report will show the failures.

---

## Phase 4 — Execute & Verify

Run all generated test files and verify they pass. If tests fail, fix them and re-run.
Max **3 iterations** per skill category.

### Run command by language

| Language | Command |
|----------|---------|
| TypeScript / JavaScript | `cd {project_root} && npx jest --json --outputFile=.qa-skills/jest-results.json 2>&1` |
| Python | `cd {project_root} && pytest --tb=short -q --json-report --json-report-file=.qa-skills/pytest-results.json 2>&1` |
| Java (Maven) | `cd {project_root} && mvn test -q 2>&1` |
| C# (.NET) | `cd {project_root} && dotnet test --logger "console;verbosity=detailed" 2>&1` |

### Parse results

**Jest:** Read `.qa-skills/jest-results.json`. Field `testResults[*].assertionResults[*]` with `status == "failed"`. Extract `failureMessages[0]`.

**pytest:** Read `.qa-skills/pytest-results.json`. Field `tests[*]` with `outcome == "failed"`. Extract `call.longrepr`.

**Maven:** Scan stdout for `Tests run:` summary lines and `FAILURE:` sections.

**dotnet test:** Scan stdout for `Failed` lines with test name + message.

### Fix loop

For each failing test:
1. Read the generated test file
2. Read the source module being tested
3. Identify root cause: wrong mock return value, wrong expected status, missing import, API signature mismatch
4. Fix **only the failing assertion/mock** — do not rewrite passing tests
5. Write the fixed file

After fixing, run again. Repeat until all tests pass or 3 iterations reached.

### After fix loop

Record execution results:
```python
context["execution_results"] = {
    "unit":     {"status": "passed | failed | partial", "iterations": N},
    "api":      {"status": "passed | failed | partial", "iterations": N},
    "security": {"status": "passed | failed | partial", "iterations": N},
    "ui":       {"status": "skipped | passed | failed", "iterations": 0},
}
```

Update `execution_result` field on each item in `context["all_test_outputs"]`.

Write checkpoint: `write_checkpoint(4, "execute", list(execution_results.keys()))`.

**Postcondition:** `context["execution_results"]` is set. At least one results file
(`.qa-skills/pytest-results.json` or `.qa-skills/jest-results.json`) exists on disk.

---

## Phase 5 — Flaky detection

**Only run if Phase 4 completed with all tests passing. Skip if any category is "failed".**

**Read `~/.claude/skills/flaky-detector/SKILL.md` and follow its instructions.**

Pass: `project_root`, `context["all_test_outputs"]`, `context["language"]`.

Capture output and store:
```python
flaky_result = invoke_flaky_detector(context)
context["flaky_tests"] = flaky_result.get("flaky_tests", [])
context["flaky_runs_completed"] = flaky_result.get("runs_completed", 0)
```

Write checkpoint: `write_checkpoint(5, "flaky_detection", ["flaky-detector"])`.

**Postcondition:** `context["flaky_tests"]` is set (may be empty list — that is a valid result).

---

## Phase 6 — State update

After execution and flaky detection, write `{project_path}/test-state.json`:

```python
import json, datetime

new_state = {
    "version": "1.0",
    "last_scan": datetime.datetime.utcnow().isoformat() + "Z",
    "run_type": run_type,
    "modules": {}
}

# Carry over unchanged modules from previous state
if old_state:
    for path, data in old_state["modules"].items():
        if path not in [m["path"] for m in changed_modules]:
            new_state["modules"][path] = data

# Add/update changed modules — include execution result
for module in changed_modules:
    tests_for_module = [
        t["path"] for skill_output in context["all_test_outputs"]
        for t in skill_output
        if t.get("source_module") == module["path"]
    ]
    exec_status = next(
        (t.get("execution_result", "not_run")
         for skill_output in context["all_test_outputs"]
         for t in skill_output
         if t.get("source_module") == module["path"]),
        "not_run"
    )
    new_state["modules"][module["path"]] = {
        "hash": module["hash"],
        "tests_generated": tests_for_module,
        "execution_result": exec_status,
        "last_updated": datetime.datetime.utcnow().isoformat() + "Z"
    }

with open(f"{project_path}/test-state.json", "w") as f:
    json.dump(new_state, f, indent=2)
```

Write checkpoint: `write_checkpoint(6, "state_update", [])`.

**Postcondition:** `{project_root}/test-state.json` exists on disk.

---

## Phase 7 — Quality Score

Compute quality score before building the report.

```python
def compute_quality_score(coverage_by_category: dict, flaky_tests: list, gaps: list) -> int:
    score = 0

    # Coverage weighted sum (max 80 points)
    weights = {"unit": 0.3, "api": 0.3, "ui": 0.2, "security": 0.2}
    for cat, weight in weights.items():
        pct = coverage_by_category.get(cat, {}).get("pct", 0)
        score += int(pct * weight * 0.8)

    # Penalties
    flaky = len(flaky_tests)
    high_gaps = len([g for g in gaps if g.get("severity") == "high"])
    score -= flaky * 2
    score -= high_gaps * 5

    # Bonuses
    if coverage_by_category.get("contract", {}).get("pct", 0) == 100:
        score += 5
    if coverage_by_category.get("a11y", {}).get("critical_violations", 1) == 0:
        score += 3

    return max(0, min(100, score))
```

Store: `context["quality_score"] = quality_score`.

Write checkpoint: `write_checkpoint(7, "quality_score", [])`.

**Postcondition:** `context["quality_score"]` is an integer 0–100.

---

## Phase 8 — Report

**Read `~/.claude/skills/coverage-reporter/SKILL.md` and follow its instructions.**

This is the SINGLE report invocation for this run. Pass ALL execution data:

- `analysis` — full analyzer output
- `test_outputs` — `context["all_test_outputs"]`
- `state` — new state just written
- `run_type`
- `project_root`
- `flaky_tests` — `context["flaky_tests"]`
- `quality_score` — `context["quality_score"]`
- `timeline` — full timeline including Phase 4 (execute) entries (see below)

`coverage-reporter` writes `report-data.json` and invokes `html-reporter` automatically.
`html-reporter` opens the browser.

### Timeline tracking

Track start/end time for every phase. Build the complete timeline:
```json
[
  { "step": "code-analyzer",    "duration_ms": 1200, "status": "done" },
  { "step": "git-diff-analyzer","duration_ms": 400,  "status": "done" },
  { "step": "env-validator",    "duration_ms": 200,  "status": "done" },
  { "step": "unit-test",        "duration_ms": 4500, "status": "done" },
  { "step": "api-test",         "duration_ms": 2100, "status": "done" },
  { "step": "ui-playwright",    "duration_ms": 0,    "status": "skipped" },
  { "step": "security-test",    "duration_ms": 1800, "status": "done" },
  { "step": "accessibility-test","duration_ms": 0,   "status": "skipped" },
  { "step": "contract-test",    "duration_ms": 0,    "status": "skipped" },
  { "step": "execute-unit",     "duration_ms": N,    "status": "passed | failed | partial", "iterations": 1 },
  { "step": "execute-api",      "duration_ms": N,    "status": "passed | failed | partial", "iterations": 1 },
  { "step": "execute-security", "duration_ms": N,    "status": "passed | failed | partial", "iterations": 1 },
  { "step": "flaky-detector",   "duration_ms": N,    "status": "done | skipped" },
  { "step": "coverage-reporter","duration_ms": 300,  "status": "done" }
]
```

Write checkpoint: `write_checkpoint(8, "report", ["coverage-reporter", "html-reporter"])`.

**Postcondition:** `{project_root}/test-reports/report-data.json` exists on disk.

---

## Phase 9 — Final gate

Before printing the summary, verify ALL four RUN COMPLETION CONTRACT artifacts exist:

```python
import os

report_data_path = os.path.join(project_root, "test-reports", "report-data.json")
report_dir = os.path.join(project_root, "test-reports")
html_files = (
    [f for f in os.listdir(report_dir) if f.endswith(".html")]
    if os.path.isdir(report_dir) else []
)
state_path = os.path.join(project_root, "test-state.json")
checkpoint_ok = os.path.exists(checkpoint_path)

missing = []
if not os.path.exists(state_path):       missing.append("test-state.json")
if not os.path.exists(report_data_path): missing.append("test-reports/report-data.json")
if not html_files:                        missing.append("test-reports/*.html")
if not checkpoint_ok:                     missing.append(".qa-skills/checkpoints/run.json")

if missing:
    # Re-invoke any missing step once, then re-check
    if "test-reports/report-data.json" in missing or "test-reports/*.html" in missing:
        # Re-invoke coverage-reporter + html-reporter
        invoke_skill("coverage-reporter", context)
    if "test-state.json" in missing:
        # Re-run Phase 6
        run_state_update(context)

    # Check again
    html_files = [f for f in os.listdir(report_dir) if f.endswith(".html")] if os.path.isdir(report_dir) else []
    still_missing = []
    if not os.path.exists(state_path):       still_missing.append("test-state.json")
    if not os.path.exists(report_data_path): still_missing.append("test-reports/report-data.json")
    if not html_files:                        still_missing.append("test-reports/*.html")
    if still_missing:
        raise RuntimeError(
            f"Run INCOMPLETE — missing artifacts after retry: {still_missing}\n"
            f"Do NOT display success summary."
        )
```

Mark checkpoint complete:
```python
with open(checkpoint_path) as f:
    cp = json.load(f)
cp["completed"] = True
cp["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
with open(checkpoint_path, "w") as f:
    json.dump(cp, f, indent=2)
```

---

## Final summary (print after Phase 9 passes)

Use message keys from `skills/_shared/messages/{locale}.json`:

**Hebrew:**
```
run_done      → "✅ הושלם. ציון איכות: {score}/100"
run_summary   → "   חדשות: {new} | עודכנו: {updated} | לא יציבות: {flaky}"
run_recommendation → "   המלצה: {gaps} פערים בעדיפות גבוהה — דוח פתוח בדפדפן."
report_opened → "📄 הדוח נפתח בדפדפן: {path}"
```

**English:**
```
run_done      → "✅ Done. Quality score: {score}/100"
run_summary   → "   New: {new} | Updated: {updated} | Flaky: {flaky}"
run_recommendation → "   {gaps} high-priority gaps — report opened in browser."
report_opened → "📄 Report opened in browser: {path}"
```

---

## Error handling

If a test skill fails for specific modules:
- Log error per module in `test_outputs`
- Continue with remaining modules — never abort the full run
- Mark module `status: "error"` in state
- Surface all errors in Timeline section of HTML report
