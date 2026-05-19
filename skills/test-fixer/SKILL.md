---
name: test-fixer
description: Heal an existing completed QA run — diagnose root-cause clusters, apply shared harness/config/seed fixes once, then fan out per-test fixers for the residue, with plateau/rollback safety and an honest baseline-vs-healed delta. Operates on a prior run's .qa-agent state; never edits app source. Triggers on "heal tests", "fix the tests", "improve test quality", "raise pass rate", "תקן בדיקות", "שפר איכות בדיקות", "העלה אחוז הצלחה".
---

# test-fixer

You heal an **already-completed** QA run: the plugin scanned, generated,
ran, and reported, but pass-rate is low because most failures share a
few root causes. Your job is to drive a diagnose → shared-fix →
fan-out → rerun loop until quality plateaus, then surface an honest
delta.

Like `test-orchestrator`, this skill is a **top-level user-facing entry
point**, so the Claude Code recursion restriction (a sub-agent cannot
spawn sub-agents) does **not** apply here. You spawn `qa-ops-diagnostician`
and `qa-test-fixer` directly via the `Agent` tool.

## Hard rules

1. **You spawn the sub-agents directly.** Use the `Agent` tool with
   `subagent_type=qa-ops-diagnostician` / `qa-test-fixer`. Never author
   the fixes yourself in this thread.
2. **Tier order is invariant.** Tier 1 (one diagnostician → shared
   fixes) → CLI rerun → re-measure → Tier 2 (per-test fan-out). Never
   fan out Tier 2 before a fresh rerun has re-measured the residue —
   shared fixes collapse whole clusters, so per-test work must run on
   the post-shared-fix residue or it wastes context.
3. **Tier 2 is parallel, one test per call.** Place every independent
   `qa-test-fixer` call in **one** assistant message. Sequential
   dispatch is a contract violation.
4. **No direct execution.** Every shell call is
   `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run heal-* ...`. Never call
   `pytest`, `npm`, `vitest`, `playwright`, or the bare `qa-agent`
   binary.
5. **State is truth.** Read the loop decision from
   `qa-skills-run heal-status`. Never recompute pass-rate yourself or
   restate it with different numbers.
6. **Honest delta.** Final numbers come from `report-data.json` after
   the CLI `report` rebuild. Product bugs are **reported, never
   patched** — the failing test stays failing/quarantined so it cannot
   raise the score.
7. **Never edit app source.** Edit scope is test files, shared
   harness/helpers, `playwright.config`/`vitest.config`, the declared
   DB seed, and dependency installs. App code is read-only. The CLI
   `heal-apply` also hard-rejects app-source targets.
8. **Never re-run `scaffold`.** Phase 6 overwrites test bodies. The
   healer edits existing bodies in place only; `heal-rerun` reuses
   `generated_tests.json` and never regenerates.

## Project root resolution

Set `PROJECT_ROOT` before any CLI call:

1. If the user supplied an explicit path, use it.
2. Else if `${PWD}` contains `package.json`, `pyproject.toml`,
   `pom.xml`, `build.gradle`, or `go.mod` — use `${PWD}`.
3. Else walk up parents until one is found, max 5 levels.
4. Else ask the user. Do not guess.

## Existing-run gate — run before anything

```bash
STATE="${PROJECT_ROOT}/.qa-agent/state"
[ -f "$STATE/execution_history.json" ] && RUNS=$(jq '.records | length' "$STATE/execution_history.json" 2>/dev/null || echo 0) || RUNS=0
[ -f "$STATE/generated_tests.json" ] && TESTS=$(jq '.entries | length' "$STATE/generated_tests.json" 2>/dev/null || echo 0) || TESTS=0
[ -d "$STATE/critique" ] && CRIT=$(ls "$STATE/critique" 2>/dev/null | wc -l | tr -d ' ') || CRIT=0
echo "heal-precheck: runs=$RUNS tests=$TESTS critique=$CRIT"
```

- `RUNS == 0` or `TESTS == 0` → **refuse**, in Hebrew:
  `אין ריצת QA קודמת לרפא — הרץ קודם 'הרץ qa'`. Do not start a pipeline.
- `RUNS > 0`, `CRIT == 0` → proceed. State once that triage (phase 9)
  may have been skipped; `heal-diagnose` clusters from execution logs
  alone and does not require `critique/*.json`.

## Phases

| #  | Phase              | Owner | Command / dispatch                                  |
|----|--------------------|-------|------------------------------------------------------|
| H0 | gate + baseline    | CLI   | the precheck above, then `heal-status` (baseline)    |
| H1 | diagnose / cluster | CLI   | `heal-diagnose`                                      |
| H2 | Tier-1 shared fix  | AGENT | 1× `qa-ops-diagnostician`                            |
| H3 | apply              | CLI   | `heal-apply` per planned shared fix                  |
| H4 | rerun (all)        | CLI   | `heal-rerun --scope all --tier systemic`             |
| H5 | re-measure         | CLI   | `heal-status` → rollback if `decision=rollback`      |
| H6 | Tier-2 fan-out     | AGENT | N× `qa-test-fixer` (one message, 1 test each)        |
| H7 | rerun (failed)     | CLI   | `heal-rerun --scope failed --tier per_test`          |
| H8 | iterate / stop     | SKILL | `heal-status`; loop or finish                        |
| H9 | report             | CLI   | `report --open`                                      |

## The loop

For global iteration `n` (the CLI caps it at 4):

1. `heal-diagnose` — re-clusters the **current** residue. Read the JSON
   summary: `systemic_clusters[]` and per-test counts.
2. **Tier 1** — if any systemic cluster exists and was not already
   attempted this run, dispatch **one** `qa-ops-diagnostician` with the
   `heal_clusters.json` path. It writes shared fixes as a plan +
   applies harness/config/seed edits. Then `heal-apply` each entry it
   could not write itself (e.g. `--kind dep`), passing
   `--iteration n`.
3. `heal-rerun --scope all --iteration n --tier systemic`.
4. `heal-status`. If `decision=rollback`:
   `heal-apply --revert n --project ...`, re-run
   `heal-rerun --scope all`, mark this shared plan rejected, and **do
   not retry the same shared fix** — go straight to Tier 2.
5. **Tier 2** — read `heal_clusters.json` `per_test[]`. Skip any
   cluster with `is_prod_bug=true` (those are reported, not fixed) and
   any test whose `retry_budget.json` entry is exhausted/frozen. Fan
   out the rest as `qa-test-fixer`, **one test per call, all in one
   message**.
6. `heal-rerun --scope failed --iteration n --tier per_test`.
7. `heal-status`. Stop the loop when `decision` ∈
   {`plateau`, `cap`, `done`}. Otherwise continue to iteration `n+1`.

Sub-agent prompt — `qa-ops-diagnostician` (Tier 1, exactly one):

> Project root: `${PROJECT_ROOT}`. Iteration: `<n>`.
> Read `state/heal_clusters.json` (systemic clusters), the sampled
> per-test logs under `.qa-agent/runs/<run_id>/logs/`, the relevant
> `state/contracts/<cap>.json`, and `state/ui_selectors.json`.
> Apply ONE shared fix per systemic cluster (global-setup/storageState,
> shared fixture/token map, DB seed, framework config). Emit
> `state/heal_shared_fix_plan.json` and route any dependency installs
> back to me as `--kind dep`. Report product bugs into
> `reported_prod_bugs[]` and write `state/critique/<test_id>.json`
> with `verdict:prod-bug` — never patch app source.

Sub-agent prompt — `qa-test-fixer` (Tier 2, one per residual test):

> Project root: `${PROJECT_ROOT}`. Failing test id: `<test_id>`.
> Test path: `<test_path>`. Log:
> `.qa-agent/runs/<run_id>/logs/<safe_test_id>.log`.
> Read the log first, then the test file, the scenario in
> `state/scenarios/<cap>.json`, the contract in
> `state/contracts/<cap>.json`, and (ui/a11y only)
> `state/ui_selectors.json`. Decide test-bug vs prod-bug. Apply a
> bounded fix to this one test if test-bug & confidence ≥ 0.75; emit a
> `report_bug` verdict for prod-bug. Never touch sibling tests or
> shared harness.

## Output style

When the loop finishes, surface to the user **in Hebrew**:

- פתח עם הוורדיקט: אחוז העברה התחלתי → אחוז העברה אחרי ריפוי (מתוך
  `report-data.json` — לא מספרים שאתה מחשב).
- נתיב דוח ה-HTML בשורה אחת, לחיץ.
- **תוקן**: התיקונים המשותפים שיושמו + מספר תיקוני פר-טסט שהפכו
  fail→pass.
- **באגים אמיתיים שדווחו (לא תוקנו)**: כל `prod-bug` מתוך
  `critique/*.json` עם `code_location_at_fault`, מסומן מפורשות
  שהוצא מהציון בכוונה.
- **לא ניתן לתקן**: שאריות שתקציב התיקון שלהן מוצה.
- עצור. בלי סופות bullets.

Technical ids, capability slugs, route patterns, and CLI log lines stay
in English; the prose is Hebrew.

## First-run latency

The first `qa-skills-run` call after install builds the plugin venv
under `${CLAUDE_PLUGIN_ROOT}/.venv` (~20–40 s). Subsequent calls reuse
it.
