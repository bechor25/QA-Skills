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
dispatches test generation to sub-skills, runs tests, fixes failures, and produces an HTML report.

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

## Sub-skills location

This orchestrator delegates to the following sub-skills. When instructed to invoke a sub-skill,
read its SKILL.md file and follow its instructions.

All skills install to `~/.claude/skills/`. Read from there:

```
~/.claude/skills/code-analyzer/SKILL.md
~/.claude/skills/coverage-reporter/SKILL.md
~/.claude/skills/html-reporter/SKILL.md
~/.claude/skills/unit-test/SKILL.md
~/.claude/skills/api-test/SKILL.md
~/.claude/skills/security-test/SKILL.md
~/.claude/skills/ui-playwright/SKILL.md
```

If `~/.claude/skills/` is not found (non-standard install), locate the skill directory by running:
```bash
find ~ -name "code-analyzer" -path "*/skills/*" -type d 2>/dev/null | head -1 | xargs dirname
```

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_path` | Yes | Absolute path to the project root |
| `force_full` | No | If `true`, ignore state and regenerate all tests |
| `categories` | No | Limit to specific skills: `["unit", "api", "ui", "security"]` |

Ask the user for `project_path` if not provided. Do not assume CWD.

---

## Phase 1 — Scan

**Read `~/.claude/skills/code-analyzer/SKILL.md` and follow its instructions on `project_path`.**

Capture full JSON output as `analysis`. Display to user (in their language):
```
Scanning {project_path}...
Found: {stats.total_files} files | {language} |
  {stats.has_api ? "API ✓" : ""} {stats.has_frontend ? "UI ✓" : ""}
  {stats.has_db ? "DB ✓" : ""} {stats.has_auth ? "Auth ✓" : ""}
```

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

If `changed_modules + new_modules` is empty:
→ Tell user "No changes detected since last run. Use force_full=true to regenerate all."
→ Still run coverage-reporter and html-reporter with existing data.
→ Exit early after report.

Display:
```
State found. Changed: {len(changed_modules)} | New: {len(new_modules)} | Unchanged: {unchanged_count}
Running incremental update...
```

**If no state file:**
- `changed_modules` = all modules in `analysis["modules"]`
- Display: `No prior state. Running full scan...`

**`run_type`** = `"incremental"` if state existed, `"full"` otherwise.

---

## Phase 3 — Dispatch

Based on `analysis` and `changed_modules`, decide which skills to invoke.

### Decision matrix

| Condition | Skill |
|-----------|-------|
| Always | `unit-test` |
| `analysis.stats.has_frontend == true` AND changed modules include frontend files | `ui-playwright` |
| `analysis.routes` non-empty AND changed modules include controller/route files | `api-test` |
| Any changed module has `has_auth: true` OR `has_db_queries: true` OR non-empty `input_fields` | `security-test` |

Override: if `categories` parameter provided, only dispatch listed categories.

### How to invoke each skill

For each skill to invoke, **read its SKILL.md from `~/.claude/skills/<skill-name>/SKILL.md`**
and follow its instructions. Pass the following input:

```json
{
  "modules": ["only changed_modules relevant to this skill"],
  "routes": ["from analysis, filtered to changed controllers"],
  "project_root": "string",
  "language": "string",
  "run_type": "full | incremental"
}
```

Run `unit-test`, `ui-playwright`, `api-test`, `security-test` **in parallel** when all inputs are ready.

Collect output from each: list of `{ file, tests_written, path, source_module }`.

---

## Phase 4 — State update

After all test skills complete, write `{project_path}/test-state.json`:

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

# Add/update changed modules
for module in changed_modules:
    tests_for_module = [
        t["path"] for skill_output in all_test_outputs
        for t in skill_output
        if t.get("source_module") == module["path"]
    ]
    new_state["modules"][module["path"]] = {
        "hash": module["hash"],
        "tests_generated": tests_for_module,
        "last_updated": datetime.datetime.utcnow().isoformat() + "Z"
    }

with open(f"{project_path}/test-state.json", "w") as f:
    json.dump(new_state, f, indent=2)
```

---

## Phase 5 — Report

**Read `~/.claude/skills/coverage-reporter/SKILL.md` and follow its instructions.**

Pass:
- `analysis` (full analyzer output)
- `test_outputs` (collected from all skills)
- `state` (new state just written)
- `run_type`
- `project_root`
- `timeline` (see below)

`coverage-reporter` produces `report-data.json` and invokes `html-reporter` automatically.

## Timeline tracking

Track start/end time for each phase. Pass to `coverage-reporter`:
```json
"timeline": [
  { "step": "code-analyzer",    "duration_ms": 1200, "status": "done" },
  { "step": "unit-test",        "duration_ms": 4500, "status": "done" },
  { "step": "api-test",         "duration_ms": 2100, "status": "done" },
  { "step": "ui-playwright",    "duration_ms": 0,    "status": "skipped" },
  { "step": "security-test",    "duration_ms": 1800, "status": "done" },
  { "step": "coverage-reporter","duration_ms": 300,  "status": "done" }
]
```

---

## Phase 6 — Execute & Verify

After Phase 5 (report), run all generated test files and verify they pass.
If tests fail, fix them and re-run. Max **3 iterations** per skill category.

### Run command by language

| Language | Command |
|----------|---------|
| TypeScript / JavaScript | `cd {project_root} && npx jest --json --outputFile=jest-results.json 2>&1` |
| Python | `cd {project_root} && pytest --tb=short -q --json-report --json-report-file=pytest-results.json 2>&1` |
| Java (Maven) | `cd {project_root} && mvn test -q 2>&1` |
| C# (.NET) | `cd {project_root} && dotnet test --logger "console;verbosity=detailed" 2>&1` |

### Parse results

**Jest:** Read `jest-results.json`. Field `testResults[*].assertionResults[*]` with `status == "failed"`. Extract `failureMessages[0]`.

**pytest:** Read `pytest-results.json`. Field `tests[*]` with `outcome == "failed"`. Extract `call.longrepr`.

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

Append to timeline:
```json
{ "step": "execute-unit",     "duration_ms": N, "status": "passed | failed | partial", "iterations": 1 }
{ "step": "execute-api",      "duration_ms": N, "status": "passed | failed | partial", "iterations": 2 }
{ "step": "execute-security", "duration_ms": N, "status": "passed | failed | partial", "iterations": 1 }
{ "step": "execute-ui",       "duration_ms": N, "status": "skipped | passed | failed", "iterations": 0 }
```

Re-invoke `html-reporter` with updated timeline so report reflects execution status.

---

## Error handling

If a test skill fails for specific modules:
- Log error per module in `test_outputs`
- Continue with remaining modules — never abort the full run
- Mark module `status: "error"` in state
- Surface all errors in Timeline section of HTML report

---

## Final summary (print after report opens)

**Hebrew:**
```
✅ הושלם.
   בדיקות חדשות: {new_count}
   עודכנו: {updated_count}
   ללא שינוי: {unchanged_count}
   📄 דוח: {report_path}
```

**English:**
```
✅ Done.
   New tests:   {new_count}
   Updated:     {updated_count}
   Unchanged:   {unchanged_count}
   📄 Report:   {report_path}
```
