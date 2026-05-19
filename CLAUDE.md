# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This repo is **itself a Claude Code plugin** (`qa-skills`), not an app under test. It ships
skills + LLM agents that drive a Python engine (`qa-agent`) to scan a *target* project,
generate tests, run them, triage failures, and emit an HTML report. The target project is
always some *other* codebase the user opens Claude Code in — never this repo.

## Commands

```bash
pip install -e '.[parsing,dev]'   # dev install (parsing extra = tree-sitter)
pytest qa_agent/tests             # full test suite (pytest config in pyproject.toml)
pytest qa_agent/tests/test_state.py::test_name   # single test
```

There is no separate lint step configured. `pytest` `addopts` is `-q`; `testpaths` is fixed
to `qa_agent/tests`.

The runtime entry point is **not** `qa-agent` directly. Plugin invocations go through
`bin/qa-skills-run <subcommand>`, which calls `bin/qa-skills-bootstrap.sh` to lazily build an
isolated venv at `${CLAUDE_PLUGIN_ROOT}/.venv` on first use and `exec`s the installed
`qa-agent` binary. CLI subcommands: `analyze prepare build-strategy scaffold run-tests
retry-decide rerun report state full-run` (all accept `--project PATH`).

## Architecture

Four layers, strictly separated — read `ARCHITECTURE.md` for the full map:

- **Skill layer** (`skills/*/SKILL.md`) — user-facing entry. `test-orchestrator` is the
  top-level orchestrator; `analyze-project`, `rerun`, `view-report` map to single CLI
  subcommands. Skills decide *which* pipeline to run, not how.
- **CLI layer** (`qa_agent/cli/commands/*`) — all deterministic work: scanning, risk
  ranking, scaffolding, execution, healing, reporting. Pure Python, no LLM.
- **Agent layer** (`agents/*.md`) — bounded LLM authoring only: `qa-capability-mapper`,
  `qa-enricher`, `qa-scenario-author`, `qa-body-author`, `qa-triage`, `qa-probe-analyzer`.
  Each reads state files and writes only its own scoped artifact.
- **State layer** (`qa_agent/state/`) — the source of truth between every phase.

### State is the contract between phases

All inter-phase data lives under `<target-project>/.qa-agent/state/` as JSON.
`qa_agent/state/manager.py` is the *only* supported read/write path; it maps typed
Pydantic models in `qa_agent/state/schemas.py` to files. Never read/write these JSONs
directly from other modules. The dependency chain (each derived from the previous):

```
project_map → dependency_graph → knowledge_graph → risk_matrix
  → raw_capability_map → capability_map → strategy
  → contracts/<cap> → scenarios/<cap> → generated_tests
  → execution_history → critique/<test_id> → report-data → report.html
```

Because state is the contract, the pipeline is **resumable**: `test-orchestrator` inspects
existing state and restarts from the latest valid phase. Re-running `scaffold` *overwrites*
test files and wipes any authored bodies — treat phase 6 as destructive.

### Orchestration rules (critical)

The 12-phase pipeline alternates CLI and AGENT phases. The orchestrator (top-level Claude
running `test-orchestrator`) must spawn sub-agents itself via the `Agent` tool — Claude Code
forbids recursive sub-agent dispatch, so a wrapper agent cannot fan these out. For
per-capability / per-failing-test phases (enrich, scenarios, bodies, triage), place all
independent `Agent` calls **in one assistant message** to run them in parallel; the
orchestrator must never author contracts/scenarios/bodies/triage inline (context isolation
per slice is the entire point).

### Engine module map

`qa_agent/`: `scanners/` (fs, tech stack, deps, API, UI, selectors) → `parsers/` (Python
AST, tree-sitter, ts-morph bridge) → `context/` (knowledge graph, summarizer, chunking) →
`quality/` (capability discovery, risk, strategy, scenarios, validators) → `generators/`
(per-category test emit + scaffold) → `runtime/` (workspace, install planner, process) →
`executors/` (pytest/jest/vitest/playwright/maven/gradle/security/a11y) → `flaky/` +
`healing/` (re-run classification, bounded auto-fix) → `report/` (state-driven data +
`reports/enterprise.html.j2`). `agent/` holds the retry budget/engine and execution
controller used by `retry-decide`.

## Config

Defaults in `configs/defaults.yaml`; target projects override at
`<project>/.qa-agent/config.yaml`. Supported target languages: TypeScript/JavaScript,
Python, Java. Test categories: api, ui, security, accessibility, performance, regression.

## Conventions

- All asset paths inside skills/agents resolve through `${CLAUDE_PLUGIN_ROOT}`.
- Skills are bilingual (English + Hebrew triggers) — see `AGENT.md` for the trigger table;
  keep both languages in sync when editing skill descriptions.
- The HTML report and `report-data.json` are the authoritative verdict. Never restate
  quality scores with different numbers in prose.
