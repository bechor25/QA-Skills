# CLAUDE.md

Guidance for Claude Code (claude.ai/code) and any other coding agent working in this
repository. Read this file first, then `ARCHITECTURE.md` for the full engine map.

## Overview

This repo is **itself a Claude Code plugin** (`qa-skills`), not an app under test. It ships
skills + LLM agents that drive a Python engine (`qa-agent`) to scan a *target* project,
generate tests, run them, triage failures, heal them, and emit an HTML report. The target
project is always some *other* codebase the user opens Claude Code in — never this repo, so
never point the pipeline at this working directory.

Two user-facing entry points:

- `test-orchestrator` — full 12-phase QA run (scan → generate → run → triage → report).
- `test-fixer` — heal loop over an already-completed run.

## Tech stack

| Layer | Technology |
|---|---|
| Engine | Python ≥ 3.11, Pydantic v2 (state models), PyYAML (config), Jinja2 (report), Rich (CLI output) |
| Parsing | Python `ast`, tree-sitter (`parsing` extra), ts-morph bridge (Node, invoked out-of-process) |
| Tests (this repo) | pytest ≥ 8, pytest-cov |
| Packaging | setuptools via `pyproject.toml`; console script `qa-agent` |
| Target-project runners | pytest, jest, vitest, playwright, maven, gradle |
| Skill/agent layer | Markdown with YAML frontmatter (`skills/*/SKILL.md`, `agents/*.md`) |

Supported target languages: TypeScript/JavaScript, Python, Java.

## Structure

```
.claude/            agents, commands, rules, hooks settings for working ON this repo
.github/            copilot instructions, path-scoped instructions, prompts, CI workflows
agents/             plugin sub-agents shipped to users (qa-enricher, qa-triage, …)
skills/             plugin skills shipped to users (SKILL.md + references/)
bin/                qa-skills-run wrapper + venv bootstrap
configs/            defaults.yaml (target projects override under .qa-agent/config.yaml)
prompts/            shared prompt fragments
qa_agent/           the Python engine (see "Engine module map" below)
qa_agent/tests/     pytest suite — the only testpath
reports/            enterprise.html.j2 report template
scripts/            setup.sh + hooks used by .claude/settings.json
```

## Commands

```bash
scripts/setup.sh                  # one-shot bootstrap: venv + editable install with extras
pip install -e '.[parsing,dev]'   # dev install (parsing extra = tree-sitter)
python -m build                   # build the distributable package (requires `pip install build`)
pytest qa_agent/tests             # full test suite (pytest config in pyproject.toml)
pytest qa_agent/tests/test_state.py::test_name   # single test
```

There is no lint step configured, so `pytest` is the whole gate. `addopts` is `-q`;
`testpaths` is fixed to `qa_agent/tests`.

The runtime entry point is **not** `qa-agent` directly. Plugin invocations go through
`bin/qa-skills-run <subcommand>`, which calls `bin/qa-skills-bootstrap.sh` to lazily build an
isolated venv at `${CLAUDE_PLUGIN_ROOT}/.venv` on first use and `exec`s the installed
`qa-agent` binary. CLI subcommands: `analyze prepare build-strategy scaffold run-tests
retry-decide rerun report state full-run heal-diagnose heal-apply heal-rerun heal-status`
(all accept `--project PATH`).

## Verification loop (required)

1. Make the change.
2. Run `pytest qa_agent/tests` after **every** change, because the state schemas are shared
   across ~15 modules and a rename that looks local usually breaks a downstream phase.
3. If anything fails, fix and re-run — iterate until the suite is green. Do not stop at the
   first plausible diff, and do not hand back a red suite.
4. When you claim a fix works, paste the actual command output (the pytest summary line) as
   evidence, so the claim is checkable instead of trusted.
5. Touched a `SKILL.md` or `agents/*.md`? Also run `scripts/hooks/check-skill-budgets.sh`
   to confirm frontmatter and body stay inside the token budgets.

Never report "done" for work you have not run, because a silent regression in the state
chain surfaces only hours later in a user's target project.

## Architecture

Four layers, strictly separated — read `ARCHITECTURE.md` for the full map:

- **Skill layer** (`skills/*/SKILL.md`) — user-facing entry. `test-orchestrator` is the
  top-level orchestrator; `analyze-project`, `rerun`, `view-report` map to single CLI
  subcommands. Skills decide *which* pipeline to run, not how, so keep procedure detail in
  `references/` files rather than in the always-loaded body.
- **CLI layer** (`qa_agent/cli/commands/*`) — all deterministic work: scanning, risk
  ranking, scaffolding, execution, healing, reporting. Pure Python, no LLM, because every
  phase here must be reproducible and testable without a model in the loop.
- **Agent layer** (`agents/*.md`) — bounded LLM authoring only: `qa-capability-mapper`,
  `qa-enricher`, `qa-scenario-author`, `qa-body-author`, `qa-triage`, `qa-probe-analyzer`,
  `qa-ops-diagnostician`, `qa-test-fixer`. Each reads state files and writes only its own
  scoped artifact.
- **State layer** (`qa_agent/state/`) — the source of truth between every phase.

### State is the contract between phases

All inter-phase data lives under `<target-project>/.qa-agent/state/` as JSON.
`qa_agent/state/manager.py` is the *only* supported read/write path; it maps typed
Pydantic models in `qa_agent/state/schemas.py` to files. Never read/write these JSONs
directly from other modules, because the manager owns atomic writes and schema validation
and bypassing it silently corrupts later phases. The dependency chain (each derived from
the previous):

```
project_map → dependency_graph → knowledge_graph → risk_matrix
  → raw_capability_map → capability_map → strategy
  → contracts/<cap> → scenarios/<cap> → generated_tests
  → execution_history → critique/<test_id> → report-data → report.html
```

Because state is the contract, the pipeline is **resumable**: `test-orchestrator` inspects
existing state and restarts from the latest valid phase. Re-running `scaffold` *overwrites*
test files and wipes any authored bodies — treat phase 6 as destructive and only fire it on
an explicit clean rebuild, otherwise hours of authored bodies are lost.

### Orchestration rules (critical)

The 12-phase pipeline alternates CLI and AGENT phases. The orchestrator (top-level Claude
running `test-orchestrator`) must spawn sub-agents itself via the `Agent` tool, because
Claude Code forbids recursive sub-agent dispatch and a wrapper agent cannot fan these out.
For per-capability / per-failing-test phases (enrich, scenarios, bodies, triage), place all
independent `Agent` calls **in one assistant message** so they run in parallel; sequential
waves were the bottleneck that left past runs ~20% authored. The orchestrator must never
author contracts/scenarios/bodies/triage inline, since context isolation per slice is the
entire point of the fan-out.

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
`<project>/.qa-agent/config.yaml`. Test categories: api, ui, security, accessibility,
performance, regression.

## Conventions

- All asset paths inside skills/agents resolve through `${CLAUDE_PLUGIN_ROOT}`, because the
  plugin is installed outside the user's project and relative paths break there.
- Skills are bilingual (English + Hebrew triggers) — see `AGENTS.md` for the trigger table.
  Keep both languages in sync when editing skill descriptions, otherwise Hebrew-speaking
  users lose the trigger entirely.
- Skill frontmatter stays under ~100 tokens and skill bodies under ~5000 tokens; push detail
  into `skills/<name>/references/*.md` so the always-loaded surface stays small.
- The HTML report and `report-data.json` are the authoritative verdict. Never restate
  quality scores with different numbers in prose, because two conflicting numbers destroy
  trust in the whole run.

## Resources

- `ARCHITECTURE.md` — full layer + module map.
- `AGENTS.md` — cross-tool agent entry point and the EN/HE trigger table.
- `USAGE.md` — end-user walkthrough; `INSTALL.md` — plugin install.
- `ROADMAP.md`, `WORKPLAN.md`, `IMPROVEMENTS.md` — planned work and rationale.
- `.claude/rules/` — path-scoped rules (state layer, skill authoring, engine code).
- `.github/instructions/` — the same rules in Copilot's `applyTo` format.
