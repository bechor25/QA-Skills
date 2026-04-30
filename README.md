# QA Skills for Claude Code

A Claude Code plugin that auto-generates, runs, and reports on tests for any codebase.
Designed for manual QA testers — no coding required.

## Quick start

**Install:**
```bash
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```

**Upgrade:**
```bash
claude plugin uninstall qa-skills
claude plugin marketplace remove qa-skills
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```
**Use** — open Claude Code in any project and type:
```
generate tests for my project
```
or in Hebrew:
```
צור בדיקות לפרויקט שלי
```

That's it. Claude will ask for the project path if needed and handle everything else.

## What you get

- Unit tests, API tests, UI tests (Playwright), security tests, accessibility tests, and contract tests — all generated and run automatically
- An HTML report with a Quality Score (0–100), coverage by category, blind spots, and recommendations
- Flaky test detection — tests re-run 3× after passing; unstable ones are flagged with a cause and fix hint
- Incremental runs — only changed files are re-tested after the first run
- Resume — if a run is interrupted, Claude picks up where it left off

## Supported languages

TypeScript / JavaScript · Python · Java · C# / .NET

## Skills in this system

| Skill | Role |
|-------|------|
| `test-orchestrator` | Main entry point — coordinates everything |
| `unit-test` | Unit tests (functions, classes, edge cases, timezone/float bugs) |
| `api-test` | API/HTTP tests — auth matrix, concurrency, schema validation |
| `ui-playwright` | E2E browser tests — flows, session, multi-tab, RTL |
| `security-test` | OWASP Top 10 + JWT confusion + SSRF + open redirect |
| `accessibility-test` | WCAG 2.1 AA — axe-core, focus order, headings, RTL |
| `contract-test` | OpenAPI schema conformance or golden-master drift |
| `flaky-detector` | Re-runs suite 3×, reports non-deterministic tests |
| `env-validator` | Checks toolchain, framework, server, DB, disk |
| `git-diff-analyzer` | Classifies changes (trivial/body/signature) |
| `code-analyzer` | Scans codebase — routes, integrations, state machines |
| `coverage-reporter` | Aggregates results + Quality Score |
| `html-reporter` | Self-contained HTML report |

## Documentation

- [USAGE.md](USAGE.md) — full usage guide (English + Hebrew)
- [AGENT.md](AGENT.md) — all trigger phrases and skill details
