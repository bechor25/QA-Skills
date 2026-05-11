# QA Agent — Claude Code Plugin

Autonomous QA system for Claude Code. A single **QA Master** agent orchestrates,
and a Python engine does the work: scanning, planning by risk, generating tests,
running them locally, healing failures, and producing an HTML enterprise report.

> v2.0 — full rewrite. See [`ROADMAP.md`](./ROADMAP.md) for the task list and progress.

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

## Development

```bash
pip install -e '.[parsing,dev]'
pytest qa_agent/tests
```

The plugin loads from this repository when installed via
`claude plugin install qa-skills`. All asset paths inside skills/agents resolve
through `${CLAUDE_PLUGIN_ROOT}`.
