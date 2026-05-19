# QA Agent Architecture

This document explains how the pieces in `QA-Skills` connect to each other.
It is a navigation map, not a task list.

## 1. Big Picture

```text
User in Claude Code
  -> skills/test-orchestrator/SKILL.md
  -> qa-agent CLI commands
  -> LLM sub-agents for bounded authoring
  -> state files under .qa-agent/state/
  -> executors / runtime
  -> report builder + HTML report
```

The system is built around a simple split:

- **Skill layer** decides which pipeline to run.
- **CLI layer** performs deterministic work.
- **Agent layer** writes scoped artifacts.
- **State layer** is the source of truth between steps.
- **Runtime/executor layer** runs tests and records results.
- **Report layer** renders the final verdict.

## 2. Component Graph

| Layer | Main files | Connects to |
|---|---|---|
| Skill entry | [skills/test-orchestrator/SKILL.md](skills/test-orchestrator/SKILL.md), [skills/test-fixer/SKILL.md](skills/test-fixer/SKILL.md) | `qa-agent` CLI, `qa-capability-mapper`, `qa-enricher`, `qa-scenario-author`, `qa-body-author`, `qa-triage`, `qa-ops-diagnostician`, `qa-test-fixer` |
| Other skills | [skills/analyze-project/SKILL.md](skills/analyze-project/SKILL.md), [skills/rerun/SKILL.md](skills/rerun/SKILL.md), [skills/view-report/SKILL.md](skills/view-report/SKILL.md) | direct CLI subcommands |
| CLI | [qa_agent/cli/__main__.py](qa_agent/cli/__main__.py) and `qa_agent/cli/commands/*` | scanners, quality, generators, runtime, executors, report, healing |
| Agents | [agents/qa-capability-mapper.md](agents/qa-capability-mapper.md), [agents/qa-enricher.md](agents/qa-enricher.md), [agents/qa-scenario-author.md](agents/qa-scenario-author.md), [agents/qa-body-author.md](agents/qa-body-author.md), [agents/qa-triage.md](agents/qa-triage.md), [agents/qa-ops-diagnostician.md](agents/qa-ops-diagnostician.md), [agents/qa-test-fixer.md](agents/qa-test-fixer.md) | sharded state files |
| State | [qa_agent/state/schemas.py](qa_agent/state/schemas.py), [qa_agent/state/manager.py](qa_agent/state/manager.py) | every other layer |
| Scanners | `qa_agent/scanners/*` | `project_map.json`, `dependency_graph.json`, `knowledge_graph.json`, `risk_matrix.json`, `raw_capability_map.json`, `ui_selectors.json` |
| Quality | `qa_agent/quality/*` | strategy, capability discovery, scenarios, validators |
| Generators | `qa_agent/generators/*` | scaffolded tests + `generated_tests.json` |
| Runtime | `qa_agent/runtime/*` | workspace, installs, process control, test-data hints |
| Executors | `qa_agent/executors/*` | `execution_history.json`, per-test logs |
| Flaky / healing | `qa_agent/flaky/*`, `qa_agent/healing/*` | failure classification, bounded fixes |
| Report | `qa_agent/report/*`, [reports/enterprise.html.j2](reports/enterprise.html.j2) | `report-data.json`, HTML report |

## 3. Request Flow

### From user text to pipeline

1. The user types a trigger phrase such as `run qa` or `צור בדיקות`.
2. `skills/test-orchestrator/SKILL.md` resolves the project root and decides whether the run is fresh or resumable.
3. The skill calls `bin/qa-skills-run` for deterministic steps.
4. The skill fans out LLM sub-agents only for the bounded authoring phases.

### Deterministic CLI phases

| Phase | Command | Reads | Writes |
|---|---|---|---|
| Scan + analyze | `qa-agent analyze` | project files | `project_map.json`, `dependency_graph.json`, `knowledge_graph.json`, `risk_matrix.json` |
| Prepare | `qa-agent prepare` | analyzer output | `raw_capability_map.json`, `ui_selectors.json`, `test_data_plan.json` |
| Build strategy | `qa-agent build-strategy` | `risk_matrix.json`, `capability_map.json` or `raw_capability_map.json` | `strategy.json` |
| Scaffold | `qa-agent scaffold` | `scenarios/<cap>.json`, `test_data_plan.json`, `ui_selectors.json` | test files, `generated_tests.json` |
| Run | `qa-agent run-tests` | `generated_tests.json` | `execution_history.json`, logs, artifacts |
| Retry decisions | `qa-agent retry-decide` | execution history, critique verdicts | JSON decisions on stdout |
| Rerun | `qa-agent rerun` | generated tests, dependency scope | updated execution history |
| Report | `qa-agent report` | state files, execution history | `report-data.json`, HTML report |

### Agent phases

| Phase | Agent | Input | Output |
|---|---|---|---|
| Capability refinement | `qa-capability-mapper` | `raw_capability_map.json`, `knowledge_graph.json` | `capability_map.json` |
| Contract enrichment | `qa-enricher` | capability map, strategy, project root | `contracts/<cap>.json` |
| Scenario authoring | `qa-scenario-author` | contract, strategy, risk matrix | `scenarios/<cap>.json` |
| Body authoring | `qa-body-author` | contract, scenarios, scaffolded file | filled test file |
| Failure triage | `qa-triage` | failing test log, test file, contract | `critique/<test_id>.json` |

### Heal sub-flow (skills/test-fixer — runs after a completed run)

A second top-level skill that improves a finished run instead of
producing one. It loops, gated by plateau / max-iterations / per-test
budget, and rolls an iteration back if it lowers the pass-rate.

| Step | Owner | Command / agent | Reads | Writes |
|---|---|---|---|---|
| Diagnose | CLI | `heal-diagnose` | failed scope, per-test logs, `critique/*` (optional) | `heal_failures.json`, `heal_clusters.json` |
| Shared fix | AGENT | `qa-ops-diagnostician` (×1) | `heal_clusters.json`, sampled logs, contracts | harness/config/seed edits, `heal_shared_fix_plan.json`, prod-bug `critique/*` |
| Apply | CLI | `heal-apply` | a patch/body or `--revert N` | target file + `heal_journal.json` snapshot |
| Rerun | CLI | `heal-rerun` | `generated_tests.json`, scope | `execution_history.json`, `heal_ledger.json` delta |
| Per-test fix | AGENT | `qa-test-fixer` (×N, parallel) | one failing test + scenario + contract | bounded test edit or `critique/<id>.json` |
| Decide | CLI | `heal-status` | `heal_ledger.json`, `retry_budget.json` | loop decision JSON (stdout, read-only) |

The deterministic half lives in `qa_agent/healing/{cluster,loop,patcher}.py`.
Edit scope is gated in `patcher.py`: tests / shared harness / framework
config / declared seed / deps are writable; application source is hard-
rejected, so a reported `prod-bug` stays failing and cannot inflate the
score.

## 4. State Relationships

`qa_agent/state/manager.py` is the only supported way to read and write state.
It maps typed models from `qa_agent/state/schemas.py` to JSON files.

### Shared state chain

```text
project files
  -> project_map
  -> dependency_graph
  -> knowledge_graph
  -> risk_matrix
  -> raw_capability_map
  -> capability_map
  -> strategy
  -> contracts
  -> scenarios
  -> generated_tests
  -> execution_history
  -> critique
  -> report-data
  -> HTML report
```

### Why the chain matters

- `project_map.json` and `dependency_graph.json` describe what exists.
- `knowledge_graph.json` compresses that into human-readable context.
- `risk_matrix.json` decides which capabilities deserve attention first.
- `raw_capability_map.json` and `capability_map.json` decide the fan-out width.
- `strategy.json` decides which test categories each capability receives.
- `contracts/<cap>.json` and `scenarios/<cap>.json` carry test intent.
- `generated_tests.json` binds each scenario to a physical file.
- `execution_history.json` and `critique/<test_id>.json` record the actual run.
- `report-data.json` and the HTML report summarize the whole run.

## 5. File Ownership

| File group | Owner | Notes |
|---|---|---|
| `project_map.json`, `dependency_graph.json` | scanners | discovered from project structure and imports |
| `knowledge_graph.json`, `risk_matrix.json`, `strategy.json` | quality | derived from scan results |
| `raw_capability_map.json`, `ui_selectors.json`, `test_data_plan.json` | prepare phase | deterministic intermediate artifacts |
| `capability_map.json` | `qa-capability-mapper` | curated capability set |
| `contracts/<cap>.json` | `qa-enricher` | backend and UI contract scope |
| `scenarios/<cap>.json` | `qa-scenario-author` | category-specific scenarios |
| `generated_tests.json` + scaffolded files | generators | test file mapping and stubs |
| `execution_history.json` | executors | run results and counts |
| `critique/<test_id>.json` | `qa-triage` | verdicts for failing tests |
| `flaky_state.json`, `retry_budget.json` | flaky / agent | stability and retry tracking |
| `report-data.json`, `report.html` | report | deterministic summary output |

## 6. Key Connections

### `test-orchestrator` -> CLI

The skill does not implement the pipeline itself. It invokes the CLI and uses
the CLI outputs as the truth source.

### CLI -> agents

The CLI writes state files. The agents read those state files and only write
their own scoped outputs.

### generators -> executors

Scaffolded files become generated tests. Executors run those files and append
results to execution history.

### executors -> healing / flaky

Failures are classified, optionally healed, and then re-run if the retry logic
allows it.

### execution -> report

The report builder reads state and execution history only. It does not infer
results from memory or from the assistant transcript.

## 7. Practical Reading Order

If you want to understand the system quickly, read in this order:

1. [README.md](README.md) for the product summary.
2. [ROADMAP.md](ROADMAP.md) for the implemented architecture and current status.
3. [skills/test-orchestrator/SKILL.md](skills/test-orchestrator/SKILL.md) for orchestration rules.
4. [qa_agent/state/schemas.py](qa_agent/state/schemas.py) for the data model.
5. `qa_agent/cli/commands/*` for the deterministic flow.

## 8. Summary

The architecture is intentionally split into:

- **entry and orchestration** in skills,
- **deterministic work** in the CLI and Python modules,
- **bounded authoring** in LLM agents,
- **persistent truth** in state JSON,
- **execution** in runtime and executors,
- **verdicts** in the report.

That separation is what keeps the pipeline resumable, inspectable, and easy to
debug.
