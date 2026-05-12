---
name: test-orchestrator
description: Drive a full QA pipeline on the current project — deterministic phases via the qa-agent CLI, LLM phases via direct fan-out to qa-enricher / qa-scenario-author / qa-body-author / qa-triage sub-agents in parallel. Triggers on "run qa", "qa run", "full qa run", "generate tests", "generate tests for my project", "הרץ qa", "הרץ בדיקות", "צור בדיקות", "צור בדיקות לפרויקט שלי".
---

# test-orchestrator

You are the **orchestrator** for a full QA run. Drive the entire
pipeline yourself — deterministic phases through the `qa-agent` CLI,
LLM phases by **fanning out sub-agents in parallel via the `Agent`
tool**. The qa-master agent that used to wrap this work is deprecated
because Claude Code restricts recursive sub-agent dispatch: a
sub-agent cannot spawn the qa-enricher / qa-scenario-author /
qa-body-author / qa-triage sub-agents. Only the top-level Claude (you,
running this skill) can.

## Hard rules

1. **You spawn the sub-agents directly.** Do not delegate to qa-master.
   Use the `Agent` tool yourself with `subagent_type=qa-enricher` etc.
2. **Fan-out, do not author.** For phases 4 / 5 / 7 / 9, spawn one
   sub-agent per capability (or per failing test) — never write
   contracts, scenarios, test bodies, or triage verdicts yourself in
   this thread. The whole point of fan-out is context isolation per
   slice; if you do the work here, context fills up and quality
   collapses.
3. **Parallel by default.** When you have N independent sub-tasks,
   place N `Agent` tool calls **inside one assistant message** so the
   runtime executes them in parallel. Sequential dispatch (one Agent
   call, await result, then the next) is a contract violation.
4. **No direct execution.** Shell commands you run for QA must be
   `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run ...` subcommands. Never
   call `pytest`, `npm`, `pip`, `playwright`, or the bare `qa-agent`
   binary.
5. **State is truth.** State files under
   `${PROJECT_ROOT}/.qa-agent/state/` are the canonical inputs and
   outputs of every phase. Never re-scan or re-classify the project
   yourself once the CLI has produced them.
6. **Honest reports.** The HTML report and `report-data.json` are the
   verdict. Surface them as-is — never restate quality scores with
   different numbers.

## Project root resolution

Before invoking the CLI, set `PROJECT_ROOT`:

1. If the user supplied an explicit path, use it.
2. Else if `${PWD}` contains `package.json`, `pyproject.toml`,
   `pom.xml`, `build.gradle`, or `go.mod` — use `${PWD}`.
3. Else walk up parents until one of those files is found, max 5
   levels.
4. Else ask the user. Do not guess.

The wrapper is at `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run`. Always
invoke it through that path so the venv bootstrap fires on first use.

## Pipeline phases

12 phases. CLI phases are pure-Python; AGENT phases require you to
dispatch sub-agents.

| #  | Phase                | Owner | Output state file                          |
|----|----------------------|-------|---------------------------------------------|
| 1  | scan                 | CLI   | `project_map.json`, `dependency_graph.json` |
| 2  | analyze              | CLI   | `knowledge_graph.json`, `risk_matrix.json`  |
| 3a | cluster-capabilities | CLI   | `raw_capability_map.json`                   |
| 3b | refine-capabilities  | AGENT | `capability_map.json`                       |
| 3c | build-strategy       | CLI   | `strategy.json`                             |
| 4  | enrich               | AGENT | `contracts/<capability>.json`               |
| 5  | author-scenarios     | AGENT | `scenarios/<capability>.json`               |
| 6  | scaffold             | CLI   | scaffolded test files + `generated_tests.json` |
| 7  | author-bodies        | AGENT | test files filled in place                  |
| 8  | run                  | CLI   | `execution_history.json` + logs             |
| 9  | triage               | AGENT | `critique/<test_id>.json`                   |
| 10 | report               | CLI   | `report.html`                               |

## Step-by-step

### Phases 1–3a (CLI)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" prepare --project "${PROJECT_ROOT}"
```

First call may take 20–40 s for venv bootstrap. After it returns,
`state/raw_capability_map.json` exists with deterministic clusters
keyed by URL prefix and UI directory.

### Phase 3b — refine capabilities (AGENT, **single** call)

Spawn **one** `Agent` call to clean the raw capability map. Each call:

- `subagent_type`: `qa-capability-mapper`.
- `description`: `"refine capabilities"`.
- `prompt`:
  > Project root: `${PROJECT_ROOT}`. Read
  > `state/raw_capability_map.json` and
  > `state/knowledge_graph.json` (project_summary +
  > features[].name/summary only). Merge near-duplicate clusters,
  > rename URL-stem clusters using the human terms in the KG, drop
  > obvious noise (favicon, robots), and emit
  > `state/capability_map.json` per the qa-capability-mapper schema.
  > Stay within the state directory. Source must be "mapper-agent".

Wait for that single sub-agent to return before the next CLI step.
There is no fan-out here — only one mapper-agent per pipeline run.

### Phase 3c — build strategy (CLI)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" build-strategy --project "${PROJECT_ROOT}"
```

Reads `state/capability_map.json` and rewrites `state/strategy.json`
with one entry per refined capability (each capability now carries
concrete `route_globs` and `ui_globs`).

Read the new `state/strategy.json` and the corresponding
`capability_map.json` to learn:

- Which capabilities exist (this is your fan-out width).
- For each capability, its `route_globs` and `ui_globs` (you will
  forward these in the enricher prompt).

### Phase 4 — enrich (AGENT, fan-out per capability)

In a **single assistant message**, issue one `Agent` tool call per
capability. Each call:

- `subagent_type`: `qa-enricher` (or `qa-skills:qa-enricher` if the
  harness reports the namespaced form).
- `description`: e.g. `"enrich <capability>"` (3–5 words).
- `prompt` (substitute the capability-specific values):
  > Capability: `<capability>`. Project root: `${PROJECT_ROOT}`.
  > route_globs: `<comma-separated globs from capability_map>`.
  > ui_globs: `<comma-separated globs from capability_map>`.
  > Glob each pattern, read the matching handler/page files (max 10
  > per side, 3000 lines per side), and emit
  > `state/contracts/<capability>.json` per the qa-enricher schema:
  > `endpoints[]` (method, path, module_path, auth_required, request,
  > response_2xx, response_4xx, side_effects, related_files) **and**
  > `ui_entry_points[]` (route, file, needs_auth, primary_actions)
  > for every UI surface inside `ui_globs`. Do not read files outside
  > the supplied globs. If both glob sets are empty, emit an empty
  > contract with `notes` explaining the gap.

After all sub-agents return:

- Verify each `state/contracts/<cap>.json` exists. Missing → re-dispatch
  just that capability.
- For any capability whose `strategy.json` entry includes `ui` or
  `accessibility`, verify `ui_entry_points` is non-empty. Empty →
  re-dispatch `qa-enricher` for that capability — but tighten
  `ui_globs` rather than asking the sub-agent to widen its scan.

### Phase 5 — author scenarios (AGENT, fan-out per capability)

Same pattern as phase 4. One assistant message, one `Agent` call per
capability with `subagent_type=qa-scenario-author`. Prompt body:

> Capability: `<capability>`. Read `state/contracts/<capability>.json`,
> the strategy entry, and `risk_matrix.json` for this capability.
> Emit `state/scenarios/<capability>.json` per the qa-scenario-author
> schema with scenarios in every category listed in
> `strategy.json`. Use payload examples from the contract's request
> schema. For ui / accessibility categories use
> `ui_entry_points[].route`, never api paths.

### Phase 6 — scaffold (CLI)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" scaffold --project "${PROJECT_ROOT}"
```

Emits **one file per `(capability, category)` pair**, each holding
multiple stubs (one per scenario). Path shape:
`tests/qa-agent/<category>/<capability>.{spec.ts|py}`. Each stub
appears inside the file as a line matching
``QA-AGENT-BODY :: <scenario_id> :: <title>`` — that is the lookup
key the body author uses. `generated_tests.json` maps every scenario
to the same file path; multiple body-author batches will edit the
same file in parallel.

### Phase 7 — author bodies (AGENT, fully parallel fan-out)

Group every scenario by `(capability, category)`. Within each group,
chunk into batches of **up to 5 scenarios**. Dispatch **all** batches
in **one assistant message** so the runtime executes them
concurrently — including batches that target the same file (body
author is required to leave sibling stubs untouched, so concurrent
edits on different scenario_ids do not collide).

**You must dispatch a body-author batch for every `(capability,
category)` pair that has at least one scenario** — `api`, `security`,
`ui`, `accessibility`, `performance`, `regression`. Skipping a
category because its scaffold looks unusual (Playwright
`test.fixme(true, …)` vs jest `it.todo(…)`) is a contract violation;
all three stub forms (`it.todo("QA-AGENT-BODY :: …")`,
`test("QA-AGENT-BODY :: …", … test.fixme(true, …))`,
`pytest.skip("QA-AGENT-BODY :: …")`) are equivalent.

Concretely: if the strategy yields 11 capabilities × 5 categories
with up to 5 scenarios per batch, you may end up dispatching ~30-50
sub-agents in a single message. That is correct. **Sequential dispatch
(wave of 5, wait, wave of 5, …) is a contract violation** — it was
the bottleneck that caused past runs to finish only ~20% of bodies
before timing out.

Prompt body for `qa-body-author`:

> Category: `<category>`. Capability: `<capability>`.
> Scenario IDs: `[<id1>, <id2>, …]` (≤5).
> Project root: `${PROJECT_ROOT}`.
> Read `state/contracts/<capability>.json`,
> `state/scenarios/<capability>.json`, `state/generated_tests.json`
> (for the scaffold file path — every scenario in this batch shares
> the same path); for ui/accessibility also `state/ui_selectors.json`.
> For each `scenario_id`, find the line containing
> `QA-AGENT-BODY :: <scenario_id> ::` and replace that single stub
> with a real body using the contract for headers/payload/assertions.
> Leave sibling stubs (other scenario_ids in the same file) **alone**
> — other batches will fill them concurrently. AAA structure, no
> shared mutable state, clear names. Stay inside `tests/qa-agent/`.

### Phase 7 verification gate — required before phase 8

After the fan-out returns, run:

```bash
grep -rln "QA-AGENT-BODY" "${PROJECT_ROOT}/tests/qa-agent/" 2>/dev/null \
  || echo "all bodies authored"
```

- `all bodies authored` → proceed to phase 8.
- Any file path printed → look up the surviving
  `QA-AGENT-BODY :: <scenario_id>` markers inside those files and
  cross-reference each `scenario_id` with
  `state/generated_tests.json`. Group the missing ids back by
  `(capability, category)` and dispatch a follow-up fan-out **in one
  message** for them. Do not call phase 8 while any
  `QA-AGENT-BODY ::` line remains — the runner will skip those
  tests and inflate the apparent skip count.

This gate is not optional. Past runs silently left ui/accessibility
scaffolds unfilled when the body-author missed an unfamiliar stub
form.

### Phase 8 — run tests (CLI)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" run-tests --project "${PROJECT_ROOT}" --skip-install
```

Use `--skip-install` when the user has confirmed the SUT environment
is already prepared. Otherwise omit. `execution_history.json` records
which tests passed/failed/skipped.

### Phase 9 — triage failures (AGENT, fan-out per failure)

Only dispatch `qa-triage` for tests with `status: failed` in
`execution_history.json`. Skip passed and skipped tests. Up to 5
concurrent.

Prompt body:

> Failing test: `<test path from execution_history>`.
> Test id: `<scenario_id from generated_tests.json>`.
> Read its source, the log at
> `runs/<latest>/logs/<test>.log`, and the handler at the path in
> `state/contracts/<capability>.json`. Compare against the contract.
> Emit verdict to `state/critique/<test_id>.json` per the qa-triage
> schema: `verdict` ∈ {`test-bug`, `prod-bug`, `flaky`, `infra`},
> `confidence`, `evidence`, `action`.

### Retry loop

After triage, ask the CLI which tests should retry:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" retry-decide --project "${PROJECT_ROOT}"
```

Returns a JSON array. For each entry with `should_retry=true`, re-run
that single test and triage again. Max 2 retries per test; the CLI
persists attempt counts in `state/retry_budget.json`.

### Phase 10 — report (CLI)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" report --open --project "${PROJECT_ROOT}"
```

Renders the HTML report and (with `--open`) opens it in the browser.

## What you must NOT do

- **NEVER** try Bash to invoke an AGENT phase. There is no
  `qa-agent enrich` / `author-scenarios` / `author-bodies` /
  `triage` subcommand. If the CLI rejects the command, that is the
  signal to use the `Agent` tool — **not** the signal to "do it
  yourself".
- **NEVER** fall back to writing contracts, scenarios, test bodies,
  or triage verdicts yourself in this thread because fan-out felt
  awkward. Saying "now dispatching N sub-agents" and then running
  Bash writes instead is the exact failure mode the architecture
  exists to prevent.
- **NEVER** call Agent with a `subagent_type` you have not seen in
  the project's available list. If a type is unknown, stop and
  surface the error — re-installing/reloading the plugin is the only
  fix.

## When a sub-agent fails

A sub-agent fails when its expected output file is missing or
malformed.

- Missing `contracts/<cap>.json` → re-dispatch `qa-enricher` once for
  that capability. Failing again → mark that capability as
  `enrich_failed` in `run.json` and continue with the rest.
- Missing `scenarios/<cap>.json` → same pattern.
- Scaffold still has `QA-AGENT-BODY` → re-dispatch `qa-body-author`
  for that specific scenario. Still empty → mark as
  `skipped: authoring failed` and continue.
- Missing triage verdict → skip retry for that test and report it as
  `triage failed — see logs`.

Never block the whole pipeline on one capability or one test.

## Other triggers

### "analyze project", "נתח פרויקט"
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" analyze --project "${PROJECT_ROOT}"
```
Then `jq -r .project_summary "${PROJECT_ROOT}/.qa-agent/state/knowledge_graph.json"`
and report the summary plus the top 3 risks from `risk_matrix.json`.

### "rerun tests", "הרץ שוב"
Ask the user for scope (`changed`, `failed`, `flaky`, `all`) if it's
ambiguous, otherwise default to `changed`.
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" rerun --scope changed --project "${PROJECT_ROOT}"
```

### "open qa report", "פתח דוח qa"
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" report --open --project "${PROJECT_ROOT}"
```

## Output style

When the pipeline finishes, surface to the user **in Hebrew**:

- פתח עם הוורדיקט: ציון איכות (0–100) + אחוז העברה.
- נתיב דוח ה-HTML בשורה אחת, לחיץ.
- 3 ה-capabilities עם הסיכון הגבוה ביותר מתוך `risk_matrix.json`.
- מספרי קבצי הטסט (סך־הכל / מולאו / נכשלו / דולגו) ומספרי כיסוי לפי
  קטגוריה (api / ui / security / accessibility / performance).
- עצור. בלי סופות bullets.

הדוח עצמו (HTML + סיכום markdown) חייב להיכתב בעברית. שמות זיהוי
טכניים (test ids, capability slugs, route patterns) ושורות לוג של
ה-CLI נשארות באנגלית.

## First-run latency

The very first `qa-skills-run` call after install creates the plugin
venv under `${CLAUDE_PLUGIN_ROOT}/.venv` and `pip install`s the
`qa-agent` package (~20–40 s). Subsequent calls reuse the venv.
