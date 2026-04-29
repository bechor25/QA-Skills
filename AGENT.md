# QA Skills — מדריך לבודק

This project contains a set of QA skills for Claude Code that automatically generate, run, and report on tests for any codebase. Designed for manual QA testers — no coding required.

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

1. **Validates environment** — checks toolchain, test framework, server availability
2. **Analyzes changes** — uses git diff to skip tests for trivial changes
3. **Scans the project** — identifies all modules, routes, integrations, state machines
4. **Generates tests** in parallel: unit, API, UI, security, accessibility, contract
5. **Runs and fixes** any failures (up to 3 attempts per category)
6. **Detects flaky tests** — re-runs 3× and reports unstable tests with cause + fix hint
7. **Computes Quality Score** (0–100) — weighted coverage minus flaky/gap penalties
8. **Produces HTML report** — opens in browser with filters, blind spots, recommendations

You only need to provide the project path. Everything else is automatic.
If the environment is missing something (no jest, server not running), you get a plain-language message — no code to fix.

## Skills in this system

| Skill | Role | Standalone? |
|-------|------|-------------|
| `test-orchestrator` | Main entry point — coordinates everything | ✅ |
| `unit-test` | Unit tests (functions, classes, TZ, float precision) | ✅ |
| `api-test` | API/HTTP tests incl. auth matrix, concurrency | ✅ |
| `ui-playwright` | E2E browser tests, RTL, session, multi-tab | ✅ |
| `security-test` | OWASP Top 10 + JWT confusion + SSRF + redirect | ✅ |
| `accessibility-test` | WCAG 2.1 AA — axe-core, focus, headings, RTL | ✅ |
| `contract-test` | OpenAPI schema conformance or golden-master drift | ✅ |
| `flaky-detector` | Re-runs suite 3×, reports non-deterministic tests | internal |
| `env-validator` | Checks toolchain, framework, server, DB, disk | internal |
| `git-diff-analyzer` | Classifies changes (trivial/body/signature) | internal |
| `code-analyzer` | Scans codebase — routes, integrations, state machines | internal |
| `coverage-reporter` | Aggregates results + quality score | internal |
| `html-reporter` | Self-contained HTML report (no server needed) | internal |

## QA Skills directory structure

```
qa-skills/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   ├── _shared/
│   │   ├── schemas/              ← JSON schemas for all data structures
│   │   ├── messages/he.json      ← Hebrew user messages
│   │   ├── messages/en.json      ← English user messages
│   │   └── validate.py           ← validation + message helper
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
├── test/
│   ├── fixtures/                 ← sample apps for self-testing
│   ├── validators/               ← self-test scripts
│   └── run_all.sh                ← runs all validators
├── AGENT.md
├── USAGE.md
└── install.sh
```

When installed (plugin or symlinks), all skills live at `~/.claude/skills/<skill-name>/`.
The orchestrator reads sub-skills from `~/.claude/skills/<skill-name>/SKILL.md`.
