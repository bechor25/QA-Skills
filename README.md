# QA Agent — Claude Code Plugin

Autonomous QA system for Claude Code. A single **QA Master** agent orchestrates,
and a Python engine does the work: scanning, planning by risk, generating tests,
running them locally, healing failures, and producing an HTML enterprise report.

> v2.0 — full rewrite. All 8 phases shipped; see [`ROADMAP.md`](./ROADMAP.md).

## Install

```bash
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```

## Use

In any project, open Claude Code and type:

```
run qa
```

or in Hebrew:

```
הרץ qa
```

Claude triggers the **test-orchestrator** skill, which shells to:

```bash
qa-agent full-run --project <cwd>
```

## CLI

```text
qa-agent full-run [--project PATH] [--categories ui,api,security,...] [--no-llm]
qa-agent analyze  [--project PATH]
qa-agent rerun    [--project PATH] [--scope flaky|changed|failed|all]
qa-agent report   [--project PATH] [--open]
qa-agent state    [--project PATH] show|reset
```

## Architecture

- **Reasoning vs. execution.** The LLM plans, designs scenarios, and critiques.
  Python scans, parses, installs, runs tests, and renders reports.
- **State first.** Every phase reads and writes JSON under
  `<project>/.qa-agent/state/`. The report is built from state files only.
- **Risk-driven.** Tests target risk-weighted capabilities (auth, payments,
  mutation flows, permissions), not endpoints.
- **Incremental.** Re-runs scope to changed modules via git diff + dependency
  graph.

See [`ROADMAP.md`](./ROADMAP.md) for the full architecture and current status.

## Supported languages

TypeScript / JavaScript · Python · Java

## What you get

- **Risk-rated test plan.** Capabilities (auth, payments, permissions,
  user-mgmt, data-export, file-upload, search, admin, api-public) scored
  on business impact × state complexity × security exposure × change
  frequency. The plan picks categories per capability.
- **Tests across 6 categories** — api (pytest / jest+supertest), ui
  (Playwright), security (OWASP-aligned), accessibility (axe-core),
  performance (p95 smoke), regression (flow replay).
- **Bounded self-healing.** Conservative fixes for selector/timeout/
  dependency failures. Assertions are never weakened.
- **Flaky detection.** Failed files re-run N times; classified into
  timing / network / env / race / order.
- **Incremental reruns.** `qa-agent rerun --scope changed` re-runs only
  tests affected by the latest diff via the dependency graph.
- **Enterprise HTML report.** Quality score (0–100, deterministic), risk
  coverage map, strategy, per-category results, flaky table, critique
  findings, installation log. Self-contained file; share it as-is.

## Components

| Layer            | Where                              | What it does                                       |
|------------------|------------------------------------|----------------------------------------------------|
| Agent (1)        | `agents/qa-master.md`              | Plans, reasons, critiques. Never runs shell itself.|
| Skills (4)       | `skills/*/SKILL.md`                | Entry points + trigger phrases (EN + HE).          |
| CLI              | `qa_agent/cli/`                    | `qa-agent full-run|analyze|rerun|report|state`     |
| Scanners         | `qa_agent/scanners/`               | filesystem, tech-stack, dep graph, api, ui         |
| Parsers          | `qa_agent/parsers/`                | python AST, tree-sitter loader, ts-morph bridge    |
| Context          | `qa_agent/context/`                | KG builder, summarizer, chunking, relevance        |
| Intelligence     | `qa_agent/quality/`                | risk engine, strategy, scenarios, critic, coverage |
| Generators       | `qa_agent/generators/`             | api / ui / security / a11y / perf / regression     |
| Executors        | `qa_agent/executors/`              | pytest, jest, playwright, maven, gradle            |
| Runtime          | `qa_agent/runtime/`                | process, workspace, install planner/manager       |
| Flaky / Healing  | `qa_agent/flaky/`, `qa_agent/healing/` | re-run + classify; bounded self-fix           |
| State            | `qa_agent/state/`                  | typed pydantic schemas + atomic JSON manager       |
| Report           | `qa_agent/report/`, `reports/`     | pure-Python data + Jinja2 HTML                     |

## Development

```bash
pip install -e '.[parsing,dev]'
pytest qa_agent/tests        # 51 tests
```

The plugin loads from this repository when installed via
`claude plugin install qa-skills`. All asset paths inside skills/agents resolve
through `${CLAUDE_PLUGIN_ROOT}`.
