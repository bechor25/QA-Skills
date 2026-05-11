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

## Architecture (v2.0 — Python-driven)

Three-layer design:

- **Skills** (`skills/`) — thin user-facing trigger entry points (~25 lines).
- **Driver** (`skills/_shared/scripts/qa_run.py`) — Python pipeline runner.
  Owns all sequencing, verification, execution, and reporting. Every phase
  is a function call against `qa_skills/*.py` modules with deterministic
  outputs and 337 pytest tests behind it.
- **Agents** (`agents/`) — bounded LLM specialists invoked by the driver.
  Each test-gen agent receives a tiny prompt scoped to **one file** at a
  time. The orchestrator agent is a thin (~100-line) Bash wrapper around
  `qa_run.py` — no LLM-level sequencing.

Why this shape:

- **Honest by construction.** The driver writes `report-data.json` directly
  via `build_report_data`; there is no path for fake quality scores or
  skipped execution. Every `agent_output_*.json` and `execution_*.json` is
  persisted by Python after the sub-agent returns.
- **Bounded LLM context.** Sub-agents see one expected_file + one
  `domain_brief` slice + ≤5 prior paths, capped at 4096 chars per prompt.
  No more "Generate all remaining" shortcuts on large projects.
- **Resumable.** `batch_state.json` makes the dispatch phase idempotent;
  killed runs pick up at the first incomplete batch.

See [ARCHITECTURE_DIAGNOSTIC.md](ARCHITECTURE_DIAGNOSTIC.md) for the v1 →
v2 rationale and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the
migration steps. See [AGENT.md](AGENT.md) for all trigger phrases.

### Pipeline phases (all driven by `qa_run.py`)

| # | Phase           | Layer  | Output on disk                          |
|---|-----------------|--------|-----------------------------------------|
| 0 | Setup           | Python | `.qa-skills/{checkpoints,logs}/`       |
| 1 | Scan            | LLM    | `logs/analysis.json` (qa-code-analyzer) |
| 2 | Strategy        | Python | `logs/strategy.json`, `logs/expected_files.json` |
| 2.7 | Domain learn  | LLM    | `logs/domain_brief_<cat>.json` (qa-domain-analyzer, per planned cat) |
| 3 | Dispatch        | LLM (file-per-Task) + Python | `logs/agent_output_*.json`, `logs/execution_*.json`, `logs/batch_state.json` |
| 5 | Flaky           | LLM    | `logs/flaky.json` (qa-flaky-detector)   |
| 5.5 | Learnings     | Python | `.qa-skills/learnings.json`, `learnings.log` |
| 6 | State write     | Python | `test-state.json`                       |
| 7 | Quality         | Python | patches `report-data.json`              |
| 8 | Build report    | Python | `test-reports/report-data.json` (v2)    |
| 8b | HTML render    | LLM    | `test-reports/report-*.html` (qa-html-reporter) |
| 9 | Final gate      | Python | `checkpoints/run.json` (`completed: true`) |

## Supported languages

TypeScript / JavaScript · Python

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
| `html-reporter` | Self-contained HTML report |

### Agents (workers)

| Agent | Model | Purpose |
|-------|-------|---------|
| `qa-orchestrator` | haiku | Thin Bash wrapper around `scripts/qa_run.py` — no LLM sequencing |
| `qa-domain-analyzer` | sonnet | Extracts per-file `behaviors[]` + `test_hints[]` so test-gen sub-agents emit per-behavior tests instead of boilerplate |
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
| `qa-html-reporter` | haiku | Renders HTML report (report-data assembled by Python driver, not by an agent) |

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
