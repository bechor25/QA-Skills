# QA-Skills — Refactor Plan: Skills + Agents Architecture

**Status:** Design draft
**Date:** 2026-05-04
**Scope:** Full refactor — no backwards compatibility constraints
**Author:** Architecture proposal for review

---

## 1. Problem Statement

The current QA-Skills implementation runs the entire QA flow (scan → generate → execute → fix → report) inside the **main Claude Code conversation context**. On medium-to-large projects this fails:

### Observed failures
- **Yesterday's incident:** A UI-only project ran for over an hour without producing a single passing test. The `ui-playwright` skill kept generating ~10 tests per spec, all failing, then entering a fix loop that kept failing, then regenerating. Context exhausted before completion.
- **Root causes identified:**
  1. All sub-skill `SKILL.md` files (~4,700 lines combined) load into the main context as the orchestrator reads them sequentially.
  2. Test code, source code, and `jest`/`pytest` output from the fix loop accumulate in the main context.
  3. The UI skill has no real **pre-flight server check** — it generates tests against a non-running server, all fail with locator errors, and the fix loop cannot recover because the root cause is environmental, not test-logic.
  4. **Big-bang generation:** the UI skill writes 8–10 tests per spec before any test has been validated. If selectors are wrong, all 10 fail simultaneously.
  5. No explicit **token budget** or **abort conditions** per phase.
  6. "Run in parallel" is claimed but actually serial (no `Task` tool dispatch).

### Goals
- **Isolate context** per worker — the orchestrator's context stays small.
- **Fail fast** on environmental issues — UI without a server should be skipped, not retried for an hour.
- **Smoke-first generation** — validate one test passes before generating a batch.
- **Visible plan** — user sees what will run before it runs.
- **Budget-bounded execution** — every agent has a token cap.
- **Cost-optimized models** — match model power to task complexity.

---

## 2. Architectural Overview

### Two-layer architecture

| Layer | Purpose | Lives in | Loaded into |
|-------|---------|----------|-------------|
| **Skills** | Trigger phrase recognition, standalone entry points | `skills/<name>/SKILL.md` | Main Claude Code context (small footprint) |
| **Agents** | Heavy logic — generation, execution, fix loops | `agents/<name>.md` | Their own subagent context (isolated) |

**Critical distinction:**
- A **skill** is loaded into the main thread the moment its trigger fires. So skills must stay tiny (~20–30 lines).
- An **agent** runs in an isolated subagent context invoked via the `Task` tool. The main thread only sees the agent's final JSON return value.

### High-level flow

```
User: "test my project"
  ↓
[main context]
test-orchestrator skill (thin, triggers on Hebrew/English phrases)
  ↓ Task(subagent_type="qa-skills:qa-orchestrator")
  ↓
[isolated context #1]
qa-orchestrator agent
  ├─ Phase 0: Setup
  ├─ Phase 1: Scan      → Task(qa-code-analyzer)
  ├─ Phase 2: State     → Task(qa-git-diff-analyzer)
  ├─ Phase 2.5: Strategy → builds plan, displays to user (auto-proceed)
  ├─ Phase 3: Dispatch (parallel)
  │   ├─ Task(qa-unit-test)        [isolated context]
  │   ├─ Task(qa-api-test)         [isolated context]
  │   ├─ Task(qa-ui-test)          [isolated context — pre-flight first]
  │   ├─ Task(qa-security-test)    [isolated context]
  │   ├─ Task(qa-a11y-test)        [isolated context]
  │   └─ Task(qa-contract-test)    [isolated context]
  ├─ Phase 5: Flaky     → Task(qa-flaky-detector)
  ├─ Phase 6: State write
  ├─ Phase 7: Quality score
  ├─ Phase 8: Report    → Task(qa-coverage-reporter)
  └─ Phase 9: Final gate
  ↓ returns JSON summary
[main context]
test-orchestrator skill displays summary, opens HTML report
```

**Key property:** at no point does test code, source code, or test execution output enter the main context. The main thread only sees:
- The trigger phrase
- A small JSON summary at the end (~2KB)
- The opened HTML report path

### Why agents (not just skills)
| Benefit | Skills-only | Agents |
|---------|-------------|--------|
| Context isolation | ✗ all loads into main | ✓ each agent has own window |
| Per-task model selection | ✗ uses session model | ✓ frontmatter `model: opus\|sonnet\|haiku` |
| Per-task tool restrictions | partial | ✓ frontmatter `tools: ...` |
| Standalone trigger | ✓ | ✗ (needs skill wrapper) |
| Loaded into main context | ✓ always | ✗ never |

**Conclusion:** keep skills as thin trigger entry points; do all real work inside agents.

---

## 3. File Layout

```
QA-Skills/
├── README.md
├── USAGE.md
├── AGENT.md
├── REFACTOR_PLAN.md            (this document)
├── install.sh                  (updated to install agents/)
│
├── skills/                     ← THIN, trigger-only
│   ├── _shared/                (kept as-is — messages, validate.py)
│   ├── test-orchestrator/SKILL.md         (~50 lines, dispatcher)
│   ├── unit-test/SKILL.md                 (~25 lines, invokes agent)
│   ├── api-test/SKILL.md                  (~25 lines)
│   ├── ui-playwright/SKILL.md             (~25 lines)
│   ├── security-test/SKILL.md             (~25 lines)
│   ├── accessibility-test/SKILL.md        (~25 lines)
│   ├── contract-test/SKILL.md             (~25 lines)
│   ├── flaky-detector/SKILL.md            (~25 lines)
│   ├── code-analyzer/SKILL.md             (~25 lines)
│   ├── env-validator/SKILL.md             (~25 lines)
│   ├── git-diff-analyzer/SKILL.md         (~25 lines)
│   ├── coverage-reporter/SKILL.md         (~25 lines)
│   └── html-reporter/SKILL.md             (~25 lines)
│
├── agents/                     ← NEW — heavy logic
│   ├── qa-orchestrator.md
│   ├── qa-code-analyzer.md
│   ├── qa-env-validator.md
│   ├── qa-git-diff-analyzer.md
│   ├── qa-unit-test.md
│   ├── qa-api-test.md
│   ├── qa-ui-test.md           ← key upgrade: pre-flight + smoke-first
│   ├── qa-security-test.md
│   ├── qa-a11y-test.md
│   ├── qa-contract-test.md
│   ├── qa-flaky-detector.md
│   ├── qa-coverage-reporter.md
│   └── qa-html-reporter.md
│
└── reference/                  ← NEW — heavy code examples
    ├── ui-test-patterns.md     (Playwright snippets, selectors, flows)
    ├── security-test-patterns.md
    ├── api-test-patterns.md
    └── unit-test-patterns.md
```

**Rationale:**
- `skills/` stays small so triggering doesn't bloat main context.
- `agents/` holds the substantial system prompts (~150–250 lines each).
- `reference/` holds the long code-example libraries that agents load *only when needed* via `Read`, never as part of the system prompt.

---

## 4. Strategy Phase (NEW — Phase 2.5)

The orchestrator builds an **execution plan** before invoking any test-generation agent. **Default mode: `auto` — proceed without asking the user.** The plan is still displayed to the user as a status message so they can see what's happening, but execution does not pause for confirmation.

### Auto vs interactive

| Mode | Behavior |
|------|----------|
| **`auto` (default)** | Plan is built and displayed, then orchestrator immediately proceeds to Phase 3. User can ^C to abort. |
| `interactive` (opt-in via `--interactive` flag or env var `QA_SKILLS_INTERACTIVE=1`) | Plan is displayed, orchestrator waits for user `y/n/edit`. |

### Plan output (JSON)

```json
{
  "summary": {
    "modules_total": 18,
    "modules_changed": 6,
    "categories_planned": ["unit", "api", "ui", "security"],
    "categories_skipped": [
      {"name": "a11y", "reason": "no live server detected"},
      {"name": "contract", "reason": "no OpenAPI spec found"}
    ]
  },
  "plan": [
    {
      "agent": "qa-unit-test",
      "model": "sonnet",
      "modules": 6,
      "estimated_tokens": 40000,
      "estimated_minutes": 3
    },
    {
      "agent": "qa-api-test",
      "model": "sonnet",
      "routes": 12,
      "estimated_tokens": 30000,
      "estimated_minutes": 2
    },
    {
      "agent": "qa-ui-test",
      "model": "opus",
      "flows": 3,
      "estimated_tokens": 60000,
      "estimated_minutes": 5,
      "preflight": {
        "server_check_url": "http://localhost:3000",
        "abort_if_no_server": true,
        "smoke_first": true
      }
    },
    {
      "agent": "qa-security-test",
      "model": "opus",
      "targets": 4,
      "estimated_tokens": 25000,
      "estimated_minutes": 2
    }
  ],
  "budgets": {
    "global_token_cap": 200000,
    "per_agent_max_tokens": 80000,
    "per_agent_timeout_seconds": 600
  },
  "abort_rules": [
    "If qa-ui-test smoke test fails → skip remaining UI batches",
    "If any agent exceeds 80K tokens → return partial result",
    "If 3+ agents fail → halt run and report"
  ],
  "mode": "auto"
}
```

### User-facing display (Hebrew)

```
תוכנית ריצה (auto):
- 18 modules, 6 השתנו
- ייוצרו: unit, api, ui, security
- ידולג: a11y (אין שרת), contract (אין OpenAPI)
- מודלים: sonnet ×2, opus ×2
- זמן משוער: ~12 דקות
- UI ייעצר אם smoke test נכשל
- מתחיל...
```

### User-facing display (English)

```
Execution plan (auto):
- 18 modules, 6 changed
- Will generate: unit, api, ui, security
- Skipped: a11y (no server), contract (no OpenAPI)
- Models: sonnet ×2, opus ×2
- Estimated: ~12 minutes
- UI will halt if smoke test fails
- Starting...
```

### Per-agent micro-plan

Inside each test-generation agent, a `plan` step runs **before** any test is generated:

```json
{
  "preflight": { "...": "..." },
  "reconnaissance": { "...": "..." },
  "test_batches": [
    {"order": 1, "name": "smoke",     "tests": 1, "must_pass_to_continue": true},
    {"order": 2, "name": "auth_flow", "tests": 3, "depends_on": "smoke"},
    {"order": 3, "name": "form_flow", "tests": 2}
  ],
  "abort_conditions": [
    "smoke fails → skip remaining batches",
    "tokens > 70K → return partial"
  ]
}
```

The agent processes batches in order, checking abort conditions after each. This bounds work even when the orchestrator's global plan is optimistic.

---

## 5. UI Test Agent — Detailed Design (key fix)

The most-burning issue. Specifying in detail because this is what failed yesterday.

### File: `agents/qa-ui-test.md`

```markdown
---
name: qa-ui-test
description: Generate Playwright E2E tests with mandatory pre-flight, live reconnaissance, and smoke-first batches.
model: opus
tools: Bash, Read, Write, Edit, Grep
---

You are the UI test generation agent. Your task is to generate Playwright tests
for a frontend application. You operate in your own isolated context.

## Hard rules (never violate)

1. **Pre-flight gate first.** Before generating any test, verify the dev server is reachable.
   If unreachable → return immediately with `status: "skipped_no_server"`. Do not generate.
2. **Live reconnaissance required.** If server is up, navigate to baseURL using Playwright
   (one-shot script) and capture DOM snapshot of forms, buttons, inputs. Save to
   `/tmp/qa-ui-recon-{run_id}.json`. Selectors must come from this snapshot, not from regex guesses.
3. **Smoke-first batching.** Generate batches in order:
   - Batch 1: `smoke.spec.ts` — single `page.goto(baseURL)` + `expect(page).toHaveTitle(/.+/)`. Run.
     - Pass → continue to Batch 2.
     - Fail → diagnose root cause (server response, base URL wrong, etc.). Return partial. **Do not generate more batches.**
   - Batch 2: auth flow (3 tests). Run. ≥1 must pass to continue.
   - Batch 3: form flow (2 tests).
   - Batch 4: a11y basics (2 tests).
4. **Token budget hard cap: 70,000.** Track cumulative output tokens. Exceeded → return partial.
5. **Visual regression off by default.** Only generate if user passes `--update-snapshots`.
6. **Multi-tab / RTL / route-mock tests off by default.** Only generate if reconnaissance
   confirms the relevant pattern exists in the app.

## Inputs (from orchestrator)

```json
{
  "run_id": "uuid",
  "project_root": "absolute path",
  "frontend_files": [...],
  "routes": [...],
  "language": "...",
  "locale": "he|en",
  "preflight": {
    "server_check_url": "http://localhost:3000",
    "abort_if_no_server": true,
    "smoke_first": true
  },
  "budgets": {
    "max_tokens": 70000,
    "max_seconds": 600
  }
}
```

## Outputs (return to orchestrator)

```json
{
  "agent": "qa-ui-test",
  "status": "completed | partial | skipped_no_server | error",
  "reason": "...",
  "batches_completed": ["smoke", "auth_flow"],
  "batches_skipped": ["form_flow", "a11y_basic"],
  "specs_written": [
    {
      "source_module": "src/components/LoginForm.tsx",
      "path": "tests/e2e/auth-login.spec.ts",
      "tests_written": 3,
      "tests_passing": 3,
      "execution_result": "passed"
    }
  ],
  "tokens_used": 42000,
  "elapsed_seconds": 180
}
```

## Phase 1: Pre-flight

```bash
curl -fsS -o /dev/null --max-time 5 "${SERVER_URL}" && echo "ok" || echo "down"
```

If `down` and `abort_if_no_server: true`:
- Return `{"status": "skipped_no_server", "reason": "Server at ${SERVER_URL} not reachable"}`.
- Do not start a server. Do not generate tests.

## Phase 2: Reconnaissance

Run a one-shot Playwright script that visits the homepage and captures DOM:

```typescript
// /tmp/qa-recon-{run_id}.ts
import { chromium } from 'playwright';
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(process.env.SERVER_URL!);
  await page.waitForLoadState('networkidle');
  const snapshot = {
    title: await page.title(),
    forms: await page.$$eval('form', forms => forms.map(f => ({
      action: f.action,
      inputs: Array.from(f.querySelectorAll('input,textarea,select')).map(el => ({
        name: (el as HTMLInputElement).name,
        id: el.id,
        type: (el as HTMLInputElement).type,
        label: el.getAttribute('aria-label')
      }))
    }))),
    buttons: await page.$$eval('button, [role=button]', btns => btns.map(b => ({
      text: b.textContent?.trim(),
      ariaLabel: b.getAttribute('aria-label')
    }))),
    links: await page.$$eval('a[href]', as => as.map(a => ({
      href: a.getAttribute('href'),
      text: a.textContent?.trim()
    })))
  };
  console.log(JSON.stringify(snapshot, null, 2));
  await browser.close();
})();
```

Save snapshot. Use it to generate **concrete selectors** (e.g., `page.getByLabel('Email address')`) rather than regex guesses.

## Phase 3: Smoke batch

Generate exactly one spec — `tests/e2e/smoke.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test('homepage loads and has a title', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/.+/);
});
```

Run: `npx playwright test tests/e2e/smoke.spec.ts --reporter=json`.
- Pass → continue.
- Fail → return `partial` with diagnostic. Do not generate more.

## Phase 4: Subsequent batches

For each batch (auth, form, a11y):
1. Generate based on reconnaissance snapshot.
2. Run with `--reporter=json`.
3. Parse results. If 0/N pass → skip remaining batches, return partial.
4. If failures: max **2 fix iterations** (not 3 — keep budget tight). Read failing test + source. Fix. Re-run.
5. After fix loop, mark batch as `passed` or `partial`.

## Phase 5: Return

Aggregate batch results. Return JSON to orchestrator. Done.
```

### Why this fixes yesterday's loop
| Old behavior | New behavior |
|--------------|--------------|
| No pre-flight; generated tests against nothing | Pre-flight first; skip if no server |
| Regex selectors `/email/i` | Concrete selectors from live DOM snapshot |
| 10 tests per spec, all generated together | Smoke batch (1 test) gates everything |
| 3 fix iterations × big batches | 2 iterations × small batches; bail on 0/N |
| Visual regression always on (always fails first run) | Off unless user opts in |
| All work in main context | Isolated agent context, only JSON returns |

---

## 6. Model Assignment

Default model per agent. Override via env vars (see §8).

| Agent | Model | Reasoning |
|-------|-------|-----------|
| `qa-orchestrator` | **sonnet** | Coordination, decisions, no heavy generation |
| `qa-code-analyzer` | **haiku** | File scanning, structured JSON output |
| `qa-env-validator` | **haiku** | Tool availability checks |
| `qa-git-diff-analyzer` | **haiku** | Diff parsing |
| `qa-unit-test` | **sonnet** | Medium-complexity test code generation |
| `qa-api-test` | **sonnet** | Code generation + schema reasoning |
| `qa-ui-test` | **opus** | DOM reasoning, smoke-first logic, fix loops |
| `qa-security-test` | **opus** | OWASP reasoning, threat modeling |
| `qa-a11y-test` | **sonnet** | axe-core + Playwright pattern application |
| `qa-contract-test` | **sonnet** | Schema matching |
| `qa-flaky-detector` | **haiku** | Re-runs + diff parsing |
| `qa-coverage-reporter` | **haiku** | JSON aggregation |
| `qa-html-reporter` | **haiku** | Template rendering |

### Estimated cost change

For a 20-module project:
- **Before refactor:** all work in main context (effectively Opus). Yesterday's failed run probably consumed 500K+ tokens with no result.
- **After refactor:** Haiku ~50K + Sonnet ~150K + Opus ~150K = balanced spend.
- **Estimated savings: 60–70%** on cost, plus stability (no more loops).

---

## 7. Skill Definitions (Thin Wrappers)

Every skill becomes a small trigger-only file. Example:

### `skills/ui-playwright/SKILL.md` (new)

```markdown
---
name: ui-playwright
description: >
  Generate E2E browser tests using Playwright. Standalone entry point for UI test generation.

  English triggers (standalone): "write UI tests", "test my frontend", "E2E tests",
  "Playwright tests", "test the login flow", "browser tests", "test user flows".

  Hebrew triggers (עברית): "כתוב בדיקות UI", "בדוק את הממשק שלי", "בדיקות E2E",
  "בדיקות Playwright", "בדוק את זרימת הלוגין", "בדיקות דפדפן", "בדוק זרימות משתמש".
---

# ui-playwright (entry point)

Standalone trigger for UI test generation. Delegates all work to the
`qa-skills:qa-ui-test` agent.

## Behavior

1. Detect locale from user message (Hebrew chars → `he`, else `en`).
2. Resolve `project_root` from user message or current working directory.
3. Invoke `qa-skills:qa-ui-test` agent via the Task tool with:
   ```json
   {
     "project_root": "...",
     "locale": "he|en",
     "preflight": {
       "server_check_url": "http://localhost:3000",
       "abort_if_no_server": true,
       "smoke_first": true
     },
     "budgets": {"max_tokens": 70000, "max_seconds": 600}
   }
   ```
4. Display the agent's JSON `status` and counts to the user as a brief summary.
   Do not echo test code.

That's it. Do not generate tests inline. Do not load Playwright patterns.
The agent owns the work.
```

All other skills follow the same template — about 25 lines each.

---

## 8. Configuration & Overrides

### Environment variables

| Variable | Effect |
|----------|--------|
| `QA_SKILLS_DEFAULT_MODEL` | Override default for all agents (e.g. `opus`, `sonnet`, `haiku`) |
| `QA_SKILLS_<AGENT>_MODEL` | Per-agent override (e.g. `QA_SKILLS_UI_MODEL=sonnet`) |
| `QA_SKILLS_INTERACTIVE` | If `1`, Strategy phase pauses for confirmation |
| `QA_SKILLS_GLOBAL_TOKEN_CAP` | Override global cap (default 200K) |
| `QA_SKILLS_AGENT_TOKEN_CAP` | Override per-agent cap (default 80K) |

### CLI flags (passed through user message)

The user can include flags in the trigger message:
- `--interactive` — pause at strategy phase
- `--update-snapshots` — enable visual regression
- `--categories=unit,api` — restrict to listed categories
- `--force-full` — ignore state, regenerate all

---

## 9. RunContext (shared between agents)

The orchestrator builds and passes this object to each subagent. Stays under 5KB.

```json
{
  "run_id": "uuid",
  "project_root": "absolute path",
  "language": "typescript|python|java|csharp",
  "additional_languages": [],
  "user_locale": "he|en",
  "categories_enabled": ["unit", "api", "ui", "security", "a11y", "contract"],
  "checkpoint_dir": "{project_root}/.qa-skills/checkpoints",
  "logs_dir": "{project_root}/.qa-skills/logs/{run_id}",
  "budgets": {
    "global_token_cap": 200000,
    "per_agent_max_tokens": 80000,
    "per_agent_timeout_seconds": 600
  },
  "mode": "auto|interactive",
  "analysis_path": "{logs_dir}/analysis.json",
  "state_path": "{project_root}/test-state.json"
}
```

**Important:** the full `analysis` JSON is **not** in `RunContext` — it is written to disk and the path is passed. Each agent reads only the slice it needs (e.g., UI agent reads `analysis.frontend_files`). This keeps payloads small.

---

## 10. Phase-by-Phase Updated Specification

| Phase | Owner | Agent invoked | Returns to orchestrator |
|-------|-------|---------------|-------------------------|
| 0 — Setup | qa-orchestrator | (none) | Directories created |
| 1 — Scan | qa-orchestrator | `qa-code-analyzer` | `analysis.json` path |
| 1.5 — Diff | qa-orchestrator | `qa-git-diff-analyzer` | Updated module list with `diff_class` |
| 1.7 — Env | qa-orchestrator | `qa-env-validator` | `categories_remaining` |
| 2 — State check | qa-orchestrator | (none — file IO) | `changed_modules` |
| **2.5 — Strategy** | **qa-orchestrator** | **(none — planning)** | **Plan JSON; auto-proceed** |
| 3 — Dispatch (parallel) | qa-orchestrator | `qa-unit-test`, `qa-api-test`, `qa-ui-test`, `qa-security-test`, `qa-a11y-test`, `qa-contract-test` | Per-agent `SkillResult` JSON |
| 4 — Execute | (subsumed into each agent) | (each agent runs and fixes its own tests) | Execution results in agent's return value |
| 5 — Flaky | qa-orchestrator | `qa-flaky-detector` | `flaky_tests` list |
| 6 — State write | qa-orchestrator | (none — file IO) | `test-state.json` written |
| 7 — Quality score | qa-orchestrator | (none — pure compute) | `quality_score` |
| 8 — Report | qa-orchestrator | `qa-coverage-reporter` → invokes `qa-html-reporter` | Report files written |
| 9 — Final gate | qa-orchestrator | (none — verification) | `completed: true` |

**Key change:** Phase 4 (Execute & Verify) is no longer a separate orchestrator phase. Each test-generation agent runs and fixes its own tests inside its own context. The orchestrator only sees the final pass/fail summary.

---

## 11. Standard SkillResult Shape

Every test-generation agent returns this shape so the orchestrator can aggregate uniformly:

```json
{
  "agent": "qa-ui-test",
  "status": "completed | partial | skipped_no_server | error",
  "reason": "string explaining status",
  "outputs": [
    {
      "source_module": "src/components/LoginForm.tsx",
      "path": "tests/e2e/auth-login.spec.ts",
      "tests_written": 3,
      "tests_passing": 3,
      "assertions_covered": ["login:happy_path", "login:invalid_credentials"],
      "execution_result": "passed | failed | partial | skipped"
    }
  ],
  "batches_completed": ["smoke", "auth_flow"],
  "batches_skipped": [],
  "tokens_used": 42000,
  "elapsed_seconds": 180,
  "warnings": []
}
```

---

## 12. Install Script Update

`install.sh` extends to copy agents:

```bash
# existing — copy skills
cp -r skills/* ~/.claude/skills/

# NEW — copy agents
mkdir -p ~/.claude/agents
cp agents/*.md ~/.claude/agents/

# NEW — copy reference patterns
mkdir -p ~/.claude/qa-skills-reference
cp -r reference/* ~/.claude/qa-skills-reference/
```

Agents become invocable via Task tool as `subagent_type: "qa-skills:qa-<name>"` (or whichever namespace the plugin is published under).

---

## 13. Migration / Implementation Order

Recommended order (each step independently testable):

1. **Create `agents/` folder** with `qa-ui-test.md` first (highest pain point).
2. **Slim down `skills/ui-playwright/SKILL.md`** to thin wrapper.
3. **Verify ui-playwright trigger correctly invokes the agent** in isolation.
4. **Create `qa-orchestrator.md`** with Phase 2.5 Strategy.
5. **Slim down `skills/test-orchestrator/SKILL.md`**.
6. **Migrate remaining test-gen skills** in this order: `unit-test`, `api-test`, `security-test`, `a11y-test`, `contract-test`.
7. **Migrate utility skills:** `code-analyzer`, `env-validator`, `git-diff-analyzer`, `flaky-detector`.
8. **Migrate reporters:** `coverage-reporter`, `html-reporter`.
9. **Update `install.sh`**.
10. **Update `README.md`, `USAGE.md`, `AGENT.md`**.
11. **End-to-end test on real medium project** (the one that failed yesterday).

---

## 14. Acceptance Criteria

The refactor is complete when:

- [ ] Running on a UI-only project with **no dev server** completes in under 60 seconds with status `skipped_no_server`.
- [ ] Running on a UI-only project with **dev server up** generates a smoke spec that passes before any other UI test is generated.
- [ ] Main context after a full run never exceeds 50K tokens (orchestrator coordination only).
- [ ] Every agent returns a `SkillResult` with `tokens_used` set.
- [ ] Strategy phase is displayed and auto-proceeds.
- [ ] Hebrew and English status messages both work.
- [ ] All four artifacts of the run completion contract still exist:
  - `test-state.json`
  - `test-reports/report-data.json`
  - `test-reports/report-{name}-{stamp}.html`
  - `.qa-skills/checkpoints/run.json` with `completed: true`

---

## 15. Open Questions / Future Work

- **Token tracking inside agents** — Claude Code does not expose live token counts to a running agent. The "70K cap" must be approximated (e.g., by character count of accumulated work, or by step count). Consider a heuristic: max 5 fix iterations × max 3 batches × max 5 specs per batch.
- **Resume across agent crashes** — current checkpoints work at the orchestrator phase level. Should agents also write per-batch checkpoints? Probably yes for `qa-ui-test` (longest-running).
- **Local model** — none planned; user is on Anthropic-only.
- **Plugin namespacing** — agents installed under `qa-skills:qa-*`. Confirm namespace at install time.

---

## 16. Summary

| Aspect | Before | After |
|--------|--------|-------|
| Where work runs | Main context | Isolated subagents |
| Skill file size | 200–650 lines each | ~25 lines each |
| Sub-skill loading | All `SKILL.md` loaded into main | Agents loaded per-Task only |
| UI failure mode | Hour-long loop, no passing test | Skipped in 60s if no server; smoke-first if server up |
| Strategy phase | Implicit dispatch matrix | Explicit plan, auto-proceed by default |
| Token cap | None | 200K global, 80K per agent |
| Model selection | One model for all (session model) | Per-agent: haiku/sonnet/opus |
| Estimated cost on 20-module project | High + frequent failures | 60–70% lower, stable |

**Mode of operation:** `auto` by default. Strategy plan is always shown, but the orchestrator never waits for user input unless `--interactive` is passed.
