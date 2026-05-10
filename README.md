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

That's it. Claude asks for the project path if missing and handles everything else.

## What you get

- Unit, API, UI (Playwright), security, accessibility, and contract tests — auto-generated and run.
- HTML report with Quality Score (0–100), coverage by category, gaps, recommendations.
- Flaky-test detection — suite re-run 3× after pass; unstable tests flagged with cause + fix hint.
- Incremental runs — only changed files re-tested after the first run.
- Resume — if a run is interrupted, picks up where it left off.

## Architecture (v2 — refactored)

Two-layer design:

- **Skills** (`skills/`) — thin trigger entry points loaded into the main Claude Code context. ~25 lines each.
- **Agents** (`agents/`) — heavy QA logic running in their own isolated subagent contexts. The main thread only sees small JSON results, never test code or `jest`/`pytest` output.

This isolation:
- Keeps the main context small even on large projects.
- Cost-optimizes — each agent runs on the right model (Haiku for parsing, Sonnet for generation, Opus for UI/security).
- Stops runaway loops — every agent has a token budget cap and pre-flight server checks.

See [AGENT.md](AGENT.md) for full design and rationale.

## Supported languages

TypeScript / JavaScript · Python · Java · C# / .NET

## Components

### Skills (trigger phrases)

| Skill | Role |
|-------|------|
| `test-orchestrator` | Main entry point — coordinates everything |
| `unit-test` | Unit tests for a file or module |
| `api-test` | API/HTTP tests |
| `ui-playwright` | E2E browser tests |
| `security-test` | OWASP-aligned security tests |
| `accessibility-test` | WCAG 2.1 AA tests |
| `contract-test` | OpenAPI / golden-master tests |
| `flaky-detector` | Re-runs suite 3× to find unstable tests |
| `env-validator` | Checks toolchain + dependencies |
| `git-diff-analyzer` | Classifies code changes |
| `code-analyzer` | Scans codebase structure |
| `coverage-reporter` | Aggregates results + Quality Score |
| `html-reporter` | Self-contained HTML report |

### Agents (workers)

| Agent | Model | Purpose |
|-------|-------|---------|
| `qa-orchestrator` | sonnet | Coordinates the full flow + Strategy phase |
| `qa-code-analyzer` | haiku | Scans codebase, writes `analysis.json` |
| `qa-env-validator` | haiku | Checks toolchain |
| `qa-git-diff-analyzer` | haiku | Classifies per-module diff severity |
| `qa-unit-test` | sonnet | Generates + runs + fixes unit tests |
| `qa-api-test` | sonnet | Generates + runs + fixes API tests |
| `qa-ui-test` | opus | Pre-flight + DOM recon + smoke-first batches |
| `qa-security-test` | opus | OWASP tests, never weakens assertions |
| `qa-a11y-test` | sonnet | WCAG axe-core tests |
| `qa-contract-test` | sonnet | Schema / golden master |
| `qa-flaky-detector` | haiku | 3× re-run analysis |
| `qa-coverage-reporter` | haiku | Builds `report-data.json` |
| `qa-html-reporter` | haiku | Renders HTML report |

## Configuration overrides

Environment variables read by the orchestrator:

- `QA_SKILLS_DEFAULT_MODEL` — override every agent's model.
- `QA_SKILLS_<NAME>_MODEL` — per-agent override (e.g., `QA_SKILLS_UI_MODEL=sonnet`).
- `QA_SKILLS_INTERACTIVE=1` — pause Strategy phase for confirmation (default: auto).
- `QA_SKILLS_GLOBAL_TOKEN_CAP` — override 200000 default.
- `QA_SKILLS_AGENT_TOKEN_CAP` — override 80000 default.

## Local development

Plugin loads from this repo via `claude plugin install qa-skills` (marketplace). All file paths inside agents resolve via `${CLAUDE_PLUGIN_ROOT}/...` — reference templates load from the plugin install dir. To iterate locally, edit files here and run `claude plugin update qa-skills`.

## Documentation

- [USAGE.md](USAGE.md) — full usage guide (English + Hebrew)
- [AGENT.md](AGENT.md) — all trigger phrases
