# QA Agent — Current Architecture Roadmap

> Living source of truth for the implemented architecture, state model, and pipeline flow.
> This document reflects the code that exists in this repository today.

## 0. Project identity

- **Name:** QA Agent / QA Skills
- **Form factor:** Claude Code plugin.
- **Canonical entry point:** `skills/test-orchestrator/SKILL.md`.
- **Legacy note:** the old `qa-master` concept is no longer the primary orchestration layer. The top-level Claude run drives the pipeline directly through the `test-orchestrator` skill.
- **Primary language:** Python 3.11+.
- **Node usage:** only where needed by the implementation stack, mainly Playwright, `ts-morph`, and JS test harnesses.
- **Execution model:** local subprocess execution with per-run isolation under `.qa-agent/runs/<run-id>/`.
- **Runtime contract:** LLMs plan, critique, and author bounded artifacts. Python code scans, writes state, plans installs, executes tests, and renders reports.

## 1. System principles

1. **Single orchestration surface.** The `test-orchestrator` skill coordinates the end-to-end run.
2. **Deterministic state first.** The CLI and agents exchange data through JSON state files under `.qa-agent/state/`.
3. **Reasoning vs. execution.** LLM agents work on contracts, scenarios, bodies, mapping, and triage; Python handles scanning and execution.
4. **Scoped reads.** Agents read only the state and source files that their role requires.
5. **Grouped generation.** Scaffolds and bodies are grouped by `(capability, category)` so edits stay bounded.
6. **Conservative healing.** Fixes are limited to deterministic, bounded mutations.
7. **Reports are derived, not invented.** `report/builder.py` reads state files; the report is not handwritten by the model.

## 2. Architecture overview

```text
Claude Code chat
  └─> skills/test-orchestrator/SKILL.md
        ├─> CLI phases via bin/qa-skills-run
        │     ├─ prepare
        │     ├─ build-strategy
        │     ├─ scaffold
        │     ├─ run-tests
        │     ├─ retry-decide
        │     ├─ rerun
        │     └─ report
        └─> LLM sub-agents
              ├─ qa-capability-mapper
              ├─ qa-enricher
              ├─ qa-scenario-author
              ├─ qa-body-author
              └─ qa-triage

CLI / agents
  ├─ scanners / parsers / context
  ├─ quality (risk, strategy, generation loop, validators)
  ├─ generators / harness
  ├─ runtime / executors / healing / flaky
  ├─ state manager + schemas
  └─ report builder + renderer
```

## 3. Repository layout

```text
QA-Skills/
├── bin/
│   └── qa-skills-run
├── agents/
│   ├── qa-capability-mapper.md
│   ├── qa-body-author.md
│   ├── qa-enricher.md
│   ├── qa-scenario-author.md
│   └── qa-triage.md
├── skills/
│   ├── analyze-project/SKILL.md
│   ├── rerun/SKILL.md
│   ├── test-orchestrator/SKILL.md
│   └── view-report/SKILL.md
├── qa_agent/
│   ├── agent/                # lifecycle, planner, retries, execution control
│   ├── cli/                  # argparse entry point and subcommands
│   ├── context/              # KG, summaries, relevance, app entry
│   ├── executors/            # pytest, jest, vitest, playwright, maven, gradle
│   ├── flaky/                # detection + classification
│   ├── generators/           # api/ui/security/a11y/perf/regression + harness
│   ├── healing/              # bounded auto-fix logic
│   ├── parsers/              # tree-sitter, python AST, ts-morph bridge
│   ├── quality/              # capability discovery, risk, strategy, critic
│   ├── report/               # report data + HTML rendering
│   ├── runtime/               # workspace, process, install planner/manager
│   ├── scanners/             # filesystem, tech stack, api, ui, selectors
│   ├── shared/               # logging, paths, config, JSON, errors, git
│   ├── state/                # schemas + typed state manager
│   └── tests/
├── configs/
│   └── defaults.yaml
├── prompts/
│   ├── critic.md
│   ├── scenario.md
│   └── strategy.md
├── reports/
│   └── enterprise.html.j2
└── README.md / USAGE.md / AGENT.md / CHANGELOG.md
```

## 4. State model

All persistent state lives under `<project>/.qa-agent/state/`. The state manager is the only supported read/write path.

| File | Owner | Purpose |
|---|---|---|
| `project_map.json` | scanners | file inventory, languages, frameworks, test runners |
| `dependency_graph.json` | scanners | module graph and imports |
| `knowledge_graph.json` | context | project summary, module summaries, features |
| `risk_matrix.json` | quality | capability risk scores and rationale |
| `raw_capability_map.json` | quality | deterministic capability clusters |
| `capability_map.json` | `qa-capability-mapper` | refined capability list |
| `strategy.json` | quality | planned categories per capability |
| `ui_selectors.json` | scanners | capability-scoped UI selectors |
| `test_data_plan.json` | runtime | detected fixture / seed strategy |
| `contracts/<capability>.json` | `qa-enricher` | capability contract |
| `scenarios/<capability>.json` | `qa-scenario-author` | rich scenario list |
| `generated_tests.json` | generators | scenario-to-file mapping |
| `critique/<test_id>.json` | `qa-triage` | per-failure verdict |
| `execution_history.json` | executors | all runs and results |
| `installation_history.json` | runtime | install attempts and outcomes |
| `flaky_state.json` | flaky | flaky classifications |
| `retry_budget.json` | agent | retry attempts per test |
| `runs/<run-id>/` | workspace | logs, artifacts, report data, HTML report |

## 5. CLI surface

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
qa-agent --version
```

### What each command does

- `analyze`: filesystem scan, tech-stack detection, dependency graph, API/UI scan, knowledge graph, risk matrix, baseline strategy.
- `prepare`: runs `analyze`, then builds `raw_capability_map.json`, `ui_selectors.json`, and `test_data_plan.json`.
- `build-strategy`: rebuilds `strategy.json` from `capability_map.json` when present, otherwise falls back to raw clusters or legacy strategy.
- `scaffold`: groups scenarios by `(capability, category)` and emits one scaffold file per group.
- `run-tests`: installs dependencies if needed, executes generated suites, and records execution history.
- `retry-decide`: turns triage and execution history into retry decisions.
- `rerun`: re-executes a scoped subset of generated tests.
- `report`: renders the latest HTML report and optionally opens it.
- `full-run`: legacy convenience path that runs the direct Python engine end-to-end without the multi-agent orchestration flow.

## 6. Canonical pipeline

The current orchestration model is the skill-driven pipeline below.

| Phase | Owner | Input | Output |
|---|---|---|---|
| 1 | CLI | project root | `project_map.json`, `dependency_graph.json` |
| 2 | CLI | scanner outputs | `knowledge_graph.json`, `risk_matrix.json` |
| 3a | CLI | project map + KG | `raw_capability_map.json`, `ui_selectors.json`, `test_data_plan.json` |
| 3b | Agent | raw capability map + KG | `capability_map.json` |
| 3c | CLI | refined capabilities + risk | `strategy.json` |
| 4 | Agent | capability map + strategy | `contracts/<cap>.json` |
| 5 | Agent | contracts + strategy + risk | `scenarios/<cap>.json` |
| 6 | CLI | scenarios | scaffolded test files + `generated_tests.json` |
| 7 | Agent | scaffolded files + scenarios | filled-in test bodies |
| 8 | CLI | generated tests | execution history + logs |
| 9 | Agent | failing tests + logs + contracts | `critique/<test_id>.json` |
| 10 | CLI | history + critique | retry decisions, reruns, report |

## 7. Implemented layers

- **Scanners:** filesystem, tech stack, dependency graph, API routes, UI routes, UI selectors.
- **Parsers:** tree-sitter loader, Python AST parsing, `ts-morph` bridge.
- **Context:** knowledge graph builder, summarizer, chunking, relevance, app entry detection.
- **Quality:** capability discovery, risk engine, strategy builder, scenario generator, generation loop, assertion and selector validators.
- **Generators:** API, UI, security, accessibility, performance, regression, plus scaffold/harness support.
- **Executors:** pytest, jest, vitest, playwright, maven, gradle, security, a11y.
- **Runtime:** isolated workspaces, process control, install planner, install manager, test data detection.
- **Healing / flaky:** bounded auto-fix, failure classification, flaky detection, retry budgeting.
- **Reporting:** state-driven data builder and HTML renderer.

## 8. Current status

### Stable and aligned

- `skills/test-orchestrator/SKILL.md` is the top-level orchestration contract.
- `qa_agent/cli/__main__.py` exposes the real command surface used by the skill.
- `qa_agent/state/schemas.py` includes the sharded contract/scenario models and the richer scenario shape.
- `qa_agent/state/manager.py` already registers the new sharded state files.
- `qa_agent/generators/scaffolds.py` and `qa_agent/cli/commands/scaffold.py` group by `(capability, category)`.
- `qa_agent/cli/commands/prepare.py` is the bridge from scan/analyze to capability discovery.
- `qa_agent/cli/commands/build_strategy.py` prefers the refined capability map and falls back safely.
- `qa_agent/cli/commands/run_tests.py`, `retry_decide.py`, `rerun.py`, and `report.py` cover the execution/reporting loop.

### Legacy or historical

- `qa-master` appears in older prose and historical notes, but it is no longer the canonical orchestrator.
- `qa-agent full-run` remains as a direct engine path for convenience and compatibility.
- Older documentation may still describe the pre-sharded or pre-skill flow; keep those docs synchronized with this roadmap.

## 9. Near-term alignment work

1. Remove or rewrite any stale references to `qa-master` in user-facing docs.
2. Keep `README.md`, `USAGE.md`, and `AGENT.md` in sync with the skill-driven pipeline.
3. Preserve the sharded state contract when adding new phases, files, or agent roles.
4. Update the roadmap whenever the CLI surface or state schema changes.

