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

## What Claude does automatically / מה קלוד עושה אוטומטית

1. Scans the project and identifies all code modules
2. Generates unit tests, API tests, UI tests, and security tests as needed
3. Runs the tests and fixes any failures (up to 3 attempts)
4. Produces an HTML coverage report and opens it in the browser

You only need to provide the project path. Everything else is automatic.

## Skills in this system

| Skill | Role |
|-------|------|
| `test-orchestrator` | Main entry point — coordinates everything |
| `unit-test` | Generates unit tests (functions, classes) |
| `api-test` | Generates API/HTTP endpoint tests |
| `ui-playwright` | Generates E2E browser tests with Playwright |
| `security-test` | Generates OWASP security tests |
| `code-analyzer` | Scans codebase structure (internal, used by orchestrator) |
| `coverage-reporter` | Aggregates results into report data (internal) |
| `html-reporter` | Generates the HTML report (internal) |

## QA Skills directory structure

```
qa-skills/
├── .claude-plugin/
│   ├── plugin.json             ← plugin metadata
│   └── marketplace.json        ← marketplace listing
├── skills/                     ← all skills live here
│   ├── test-orchestrator/SKILL.md  ← main entry point
│   ├── unit-test/SKILL.md
│   ├── api-test/SKILL.md
│   ├── security-test/SKILL.md
│   ├── ui-playwright/SKILL.md
│   ├── code-analyzer/SKILL.md
│   ├── coverage-reporter/SKILL.md
│   └── html-reporter/SKILL.md
├── AGENT.md                    ← this file
├── USAGE.md
└── install.sh                  ← for local dev (symlinks)
```

When installed (plugin or symlinks), all skills live at `~/.claude/skills/<skill-name>/`.
The orchestrator reads sub-skills from `~/.claude/skills/<skill-name>/SKILL.md`.
