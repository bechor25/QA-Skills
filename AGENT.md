# QA Skills — מדריך לבודק

This project contains a set of QA skills + agents for Claude Code that automatically generate, run, and report on tests for any codebase. Designed for manual QA testers — no coding required.

**Supported languages (v1):** TypeScript / JavaScript, Python.

## How to use / איך להשתמש

Type any of the phrases below. Claude will ask for the project path and handle everything else automatically. The result is an HTML report that opens in your browser.

### English triggers
- "generate tests for my project"
- "write tests for [path]"
- "what's my test coverage?"
- "what parts of my code are untested?"
- "update tests after my changes"
- "run tests and show me a report"

### טריגרים בעברית
- "צור בדיקות לפרויקט שלי"
- "כתוב בדיקות ל-[נתיב]"
- "מה הכיסוי של הבדיקות שלי?"
- "מה לא נבדק בקוד?"
- "עדכן בדיקות אחרי השינויים שלי"
- "הרץ בדיקות ותציג לי דוח"
- "אני רוצה בדיקות"
- "צריך בדיקות"
- "תייצר בדיקות"
- "ניתוח כיסוי בדיקות"

### Additional triggers / טריגרים נוספים

**Accessibility / נגישות:**
- "test accessibility" / "WCAG" / "a11y"
- "בדוק נגישות" / "בדיקות WCAG" / "a11y"

**Contract / חוזה:**
- "contract test" / "validate API schema" / "check OpenAPI"
- "בדיקות חוזה" / "בדוק schema" / "OpenAPI"

**Security / אבטחה:**
- "security test" / "check for vulnerabilities" / "OWASP"
- "בדיקות אבטחה" / "בדוק חולשות" / "OWASP"

## What Claude does automatically / מה קלוד עושה אוטומטית

The trigger skill invokes `qa-orchestrator` agent in an isolated context. The orchestrator runs the full flow:

1. **Setup** — creates checkpoint and log directories.
2. **Scan** — `qa-code-analyzer` agent maps modules, routes, integrations.
3. **Diff classification** — `qa-git-diff-analyzer` skips trivial changes.
4. **Environment check** — `qa-env-validator` verifies toolchain. Categories with missing prerequisites are dropped.
5. **State diff** — only changed/new modules are tested (incremental run).
6. **Strategy phase** — execution plan built and displayed; auto-proceeds by default.
7. **Generate** — test-generation agents run in parallel (each in its own isolated context):
   - `qa-unit-test`, `qa-api-test`, `qa-ui-test`, `qa-security-test`, `qa-a11y-test`, `qa-contract-test`.
   - Each agent runs and fixes its own tests; only small JSON returns to the orchestrator.
8. **Flaky detection** — `qa-flaky-detector` re-runs the suite 3× to catch unstable tests.
9. **Quality score** — weighted coverage minus flaky/gap penalties.
10. **Report** — `qa-coverage-reporter` builds `report-data.json`, then `qa-html-reporter` renders the HTML and opens it in the browser.

You only provide the project path. Everything else is automatic.

If the environment is missing something (no playwright, server not running), you get a plain-language message — no code to fix. UI tests skip immediately when no dev server is reachable; they never enter a runaway loop.

## Skills (trigger phrases) and Agents (workers)

### Skills

| Skill | Trigger context | Agent it invokes |
|-------|-----------------|------------------|
| `test-orchestrator` | Main entry — full flow | `qa-orchestrator` |
| `unit-test` | Unit tests | `qa-unit-test` |
| `api-test` | API tests | `qa-api-test` |
| `ui-playwright` | UI / E2E tests | `qa-ui-test` |
| `security-test` | Security tests | `qa-security-test` |
| `accessibility-test` | WCAG | `qa-a11y-test` |
| `contract-test` | Schema / golden masters | `qa-contract-test` |
| `flaky-detector` | Re-run analysis | `qa-flaky-detector` |
| `env-validator` | Environment check | `qa-env-validator` |
| `git-diff-analyzer` | Diff classification | `qa-git-diff-analyzer` |
| `code-analyzer` | Codebase scan | `qa-code-analyzer` |
| `coverage-reporter` | Aggregation + score | `qa-coverage-reporter` |
| `html-reporter` | HTML rendering | `qa-html-reporter` |

### Agents

| Agent | Model | Why this model |
|-------|-------|----------------|
| `qa-orchestrator` | sonnet | Coordination, no heavy generation |
| `qa-code-analyzer` | haiku | Pattern scanning, structured JSON output |
| `qa-env-validator` | haiku | Tool checks |
| `qa-git-diff-analyzer` | haiku | Diff parsing |
| `qa-unit-test` | sonnet | Code generation |
| `qa-api-test` | sonnet | Code generation |
| `qa-ui-test` | opus | DOM reasoning, smoke-first logic, fix loops |
| `qa-security-test` | opus | OWASP reasoning |
| `qa-a11y-test` | sonnet | axe-core integration |
| `qa-contract-test` | sonnet | Schema matching |
| `qa-flaky-detector` | haiku | Re-runs + diff |
| `qa-coverage-reporter` | haiku | JSON aggregation |
| `qa-html-reporter` | haiku | Template rendering |

## Configuration overrides

Environment variables read by the orchestrator at start:

| Variable | Effect |
|----------|--------|
| `QA_SKILLS_DEFAULT_MODEL` | Override every agent's model |
| `QA_SKILLS_<NAME>_MODEL` | Per-agent override (e.g., `QA_SKILLS_UI_MODEL=sonnet`) |
| `QA_SKILLS_INTERACTIVE=1` | Pause Strategy phase for confirmation |
| `QA_SKILLS_GLOBAL_TOKEN_CAP` | Override 200000 default |
| `QA_SKILLS_AGENT_TOKEN_CAP` | Override 80000 default |

CLI flags in user message:
- `--interactive` — pause at strategy phase.
- `--force-full` — ignore state, regenerate all.
- `--categories=unit,api` — restrict categories.
- `--update-snapshots` — enable visual regression for UI agent.

## Directory structure

```
qa-skills/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/                          ← thin trigger entry points
│   ├── _shared/
│   ├── test-orchestrator/SKILL.md
│   ├── unit-test/SKILL.md
│   ├── api-test/SKILL.md
│   ├── security-test/SKILL.md
│   ├── ui-playwright/SKILL.md
│   ├── accessibility-test/SKILL.md
│   ├── contract-test/SKILL.md
│   ├── flaky-detector/SKILL.md
│   ├── env-validator/SKILL.md
│   ├── git-diff-analyzer/SKILL.md
│   ├── code-analyzer/SKILL.md
│   ├── coverage-reporter/SKILL.md
│   └── html-reporter/SKILL.md
├── agents/                          ← isolated subagent workers
│   ├── qa-orchestrator.md
│   ├── qa-code-analyzer.md
│   ├── qa-env-validator.md
│   ├── qa-git-diff-analyzer.md
│   ├── qa-unit-test.md
│   ├── qa-api-test.md
│   ├── qa-ui-test.md
│   ├── qa-security-test.md
│   ├── qa-a11y-test.md
│   ├── qa-contract-test.md
│   ├── qa-flaky-detector.md
│   ├── qa-coverage-reporter.md
│   └── qa-html-reporter.md
├── reference/                       ← code patterns loaded on demand (relative to plugin root)
│   ├── ui-test-patterns.md
│   ├── unit-test-patterns.md
│   ├── api-test-patterns.md
│   ├── security-test-patterns.md
│   ├── a11y-test-patterns.md
│   ├── contract-test-patterns.md
│   ├── html-report-template.md
│   ├── learnings-schema.md
│   ├── learnings-promotion.md
│   └── messages.md
├── AGENT.md
├── README.md
└── USAGE.md
```

Installed via Claude Code plugin marketplace (`claude plugin install qa-skills`). All file paths inside agents resolve via `${CLAUDE_PLUGIN_ROOT}/...` so reference templates load from the plugin install dir — no manual install script needed.

## Test output layout (what testers see in their project)

```
${project_root}/
├── tests/
│   ├── unit/<domain mirroring src/>/        ← e.g. tests/unit/services/users/manager.test.ts
│   ├── api/<route-domain>/<tag>.api.test.*  ← e.g. tests/api/auth/login.api.test.ts
│   ├── security/<route-domain>/<category>.security.test.*
│   ├── contract/<route-domain>/<tag>.contract.test.*
│   ├── ui/                                   ← single root for all UI artifacts
│   │   ├── e2e/<domain>/*.spec.ts            (TS) — specs
│   │   ├── <domain>/test_*.py                (Python) — specs
│   │   ├── conftest.py                        (Python only)
│   │   ├── playwright-report/index.html      ← Playwright HTML report
│   │   └── test-results/                     ← screenshots, videos, traces (only on failure)
│   └── a11y/<route-domain>/*.a11y.spec.*     + axe-report/index.html + test-results/
├── test-reports/
│   ├── report-data.json                      ← machine-readable aggregate
│   └── report-<project>-<timestamp>.html     ← main HTML (links to UI/a11y artifacts above)
└── .qa-skills/
    ├── checkpoints/run.json                  ← resume support
    ├── logs/<run_id>/{analysis.json,strategy.json,...}
    ├── learnings.json                        ← per-project memory of confirmed/candidate findings
    └── learnings.log                         ← append-only audit trail
```
