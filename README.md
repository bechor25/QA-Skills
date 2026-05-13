# QA Agent - Claude Code Plugin

Autonomous QA system for Claude Code. The `test-orchestrator` skill is the
entry point, and the Python engine does the work: scanning, risk ranking,
scenario generation, test scaffolding, execution, healing, flaky detection,
triage, and HTML reporting.

> v2.1 - current architecture. See [`ROADMAP.md`](./ROADMAP.md) for the
> implemented pipeline and state model.

## Install

```bash
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```

## Use

Open Claude Code in a target project and say:

```text
run qa
```

or in Hebrew:

```text
הרץ qa
```

That triggers `skills/test-orchestrator/SKILL.md`, which drives the pipeline
through `bin/qa-skills-run`.

## Pipeline

The current flow is:

1. `prepare` - scan, analyze, discover raw capabilities, selectors, and test data hints.
2. `build-strategy` - refine capability scope and rebuild `strategy.json`.
3. `scaffold` - emit grouped test files and `generated_tests.json`.
4. `run-tests` - install if needed, execute suites, and record history.
5. `retry-decide` - turn triage and execution history into retry decisions.
6. `rerun` - re-execute a scoped subset of generated tests.
7. `report` - render the HTML report.

`full-run` remains available as a direct engine path for compatibility.

## CLI

```text
qa-agent analyze        [--project PATH]
qa-agent prepare        [--project PATH]
qa-agent build-strategy [--project PATH]
qa-agent scaffold       [--project PATH]
qa-agent run-tests      [--project PATH] [--skip-install] [--timeout SECONDS]
qa-agent retry-decide   [--project PATH]
qa-agent rerun          [--project PATH] [--scope flaky|changed|failed|all]
qa-agent report         [--project PATH] [--open]
qa-agent state          [--project PATH] show|reset
qa-agent full-run       [--project PATH] [--categories ...] [--no-llm]
```

## Architecture

- **Skill first.** `test-orchestrator` is the user-facing entry point.
- **State first.** Persistent data lives under `<project>/.qa-agent/state/`.
- **Reasoning vs. execution.** LLM agents author bounded artifacts; Python scans and runs.
- **Grouped generation.** Scaffolds and bodies are grouped by `(capability, category)`.
- **Incremental.** Reruns scope to changed, failed, flaky, or all tests.

## What you get

- **Risk-rated plan.** Capabilities are scored by impact, complexity, security exposure, and change frequency.
- **Coverage by category.** API, UI, security, accessibility, performance, and regression generation are supported.
- **Bounded self-healing.** Deterministic fixes for selector, timeout, dependency, auth, and flaky classes.
- **Flaky detection.** Re-runs and classifies unstable tests.
- **Incremental reruns.** `qa-agent rerun --scope changed` re-executes only affected tests.
- **HTML report.** Deterministic report data plus a self-contained HTML summary.

## Components

| Layer | Where | What it does |
|---|---|---|
| Skill | `skills/test-orchestrator/SKILL.md` | Top-level orchestration entry point |
| Other skills | `skills/*/SKILL.md` | Analyze, rerun, and view-report entry points |
| CLI | `qa_agent/cli/` | `analyze`, `prepare`, `build-strategy`, `scaffold`, `run-tests`, `retry-decide`, `rerun`, `report`, `state`, `full-run` |
| Scanners | `qa_agent/scanners/` | filesystem, tech stack, dependency graph, API, UI, selectors |
| Parsers | `qa_agent/parsers/` | Python AST, tree-sitter loader, ts-morph bridge |
| Context | `qa_agent/context/` | knowledge graph, summarizer, chunking, relevance, app entry |
| Quality | `qa_agent/quality/` | capability discovery, risk, strategy, scenarios, validators, generation loop |
| Generators | `qa_agent/generators/` | API, UI, security, accessibility, performance, regression, scaffold/harness |
| Executors | `qa_agent/executors/` | pytest, jest, vitest, playwright, maven, gradle, security, a11y |
| Runtime | `qa_agent/runtime/` | workspace, process, install planner, install manager, test data hints |
| Flaky / Healing | `qa_agent/flaky/`, `qa_agent/healing/` | re-run classification and bounded auto-fix |
| State | `qa_agent/state/` | typed schemas and atomic JSON manager |
| Report | `qa_agent/report/`, `reports/` | state-driven data and Jinja2 HTML rendering |

## Supported languages

TypeScript / JavaScript · Python · Java

## Development

```bash
pip install -e '.[parsing,dev]'
pytest qa_agent/tests
```

The plugin loads from this repository when installed via
`claude plugin install qa-skills`. All asset paths inside skills and agents
resolve through `${CLAUDE_PLUGIN_ROOT}`.
