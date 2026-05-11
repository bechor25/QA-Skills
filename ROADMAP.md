# QA Agent — Implementation Roadmap

> Master task list. Updated after every completed task.
> Source-of-truth for project progress. Tasks marked `[x]` are done; `[ ]` are pending; `[~]` are in progress.

## 0. Project identity

- **Name:** QA Agent (a.k.a. QA Operating System)
- **Form factor:** Claude Code plugin (installable via `claude plugin install qa-skills`). All entry points are Skills + a single QA Master Agent. The plugin ships a Python package (`qa_agent`) that does the heavy lifting; agents/skills delegate to it via `${CLAUDE_PLUGIN_ROOT}/qa_agent/...`.
- **Primary language:** Python 3.11+. Node is used **only** where mandatory (Playwright, ts-morph). Java/Maven/Gradle/pytest/jest are invoked as subprocesses inside the target project.
- **Execution model:** local subprocess execution (no Docker in v1). All runs are sandboxed to a per-run workspace directory under `.qa-agent/runs/<run-id>/`.
- **Runtime contract:** the LLM **never** runs shell commands. The Agent decides; Python executors do. The plugin is structured so reasoning and execution are physically separate processes.

## 1. Principles

1. **Single brain.** One agent (`qa-master`) orchestrates. All other "agents" are stateless skills/tools.
2. **Reasoning vs. execution.** LLM does planning, scenario design, risk reasoning, critique. Python does scanning, parsing, installs, test runs, reporting, state.
3. **State first.** Everything persistent lives in `.qa-agent/state/*.json`. Every phase reads and writes state — never in-memory passing across phase boundaries.
4. **Knowledge Graph, not raw code.** The scanner emits a hierarchical KG (project → modules → features → symbols). Prompts get summaries + targeted slices, never blobs of source.
5. **Risk-driven coverage.** Tests target risk-weighted flows, not endpoints.
6. **Incremental by default.** A re-run scopes to changed modules via git diff + dependency graph.
7. **Honest reports.** Reports are built from state files only. There is no path where the LLM produces a quality score.

## 2. High-level architecture

```
            ┌─────────────────────────────────────────────┐
            │            Claude Code (chat)               │
            │  user types: "run qa" / "צור בדיקות"      │
            └────────────────┬────────────────────────────┘
                             ▼
            ┌─────────────────────────────────────────────┐
            │   Skill: test-orchestrator (entry)          │
            └────────────────┬────────────────────────────┘
                             ▼
            ┌─────────────────────────────────────────────┐
            │   Agent: qa-master  (single brain)          │
            │   - planning, reasoning, critique only      │
            └────────────────┬────────────────────────────┘
                             ▼
            ┌─────────────────────────────────────────────┐
            │   qa_agent CLI  (Python, subprocess)        │
            │     qa-agent full-run | analyze | rerun     │
            └────────────────┬────────────────────────────┘
       ┌─────────────────────┼──────────────────────┐
       ▼                     ▼                      ▼
 ┌──────────┐         ┌───────────┐          ┌──────────────┐
 │ Scanners │         │  Engines  │          │   State JSON │
 │ Parsers  │         │  Quality  │          │   .qa-agent/ │
 │ Context  │         │  Strategy │          │              │
 └────┬─────┘         └─────┬─────┘          └──────────────┘
      │                     ▼
      │              ┌────────────┐
      │              │ Executors  │
      │              │ Runtime    │
      │              └─────┬──────┘
      ▼                    ▼
 ┌──────────────────────────────────────────────────────┐
 │                    Report Engine                     │
 │           HTML enterprise report                     │
 └──────────────────────────────────────────────────────┘
```

## 3. Directory layout

```
QA-Skills/                             # plugin root
├── .claude-plugin/                    # plugin manifest (kept)
├── agents/
│   └── qa-master.md                   # single orchestrator agent
├── skills/
│   ├── test-orchestrator/SKILL.md     # entry point ("run qa")
│   ├── analyze-project/SKILL.md
│   ├── rerun/SKILL.md
│   └── view-report/SKILL.md
├── qa_agent/                          # Python package (the engine)
│   ├── __init__.py
│   ├── cli/                           # qa-agent CLI
│   │   ├── __main__.py
│   │   └── commands/
│   │       ├── full_run.py
│   │       ├── analyze.py
│   │       ├── rerun.py
│   │       └── report.py
│   ├── agent/                         # orchestration policy
│   │   ├── orchestrator.py
│   │   ├── planner.py
│   │   ├── retry_engine.py
│   │   ├── lifecycle.py
│   │   └── execution_controller.py
│   ├── scanners/
│   │   ├── filesystem.py
│   │   ├── tech_stack.py
│   │   ├── ast_scanner.py
│   │   ├── dependency.py
│   │   ├── api_scanner.py
│   │   └── ui_scanner.py
│   ├── parsers/
│   │   ├── tree_sitter_loader.py
│   │   ├── ts_morph_bridge.py        # subprocess to Node helper
│   │   ├── python_ast.py
│   │   └── semantic.py
│   ├── context/
│   │   ├── kg_builder.py             # knowledge graph
│   │   ├── summarizer.py
│   │   ├── chunking.py
│   │   └── relevance.py
│   ├── quality/
│   │   ├── risk_engine.py
│   │   ├── strategy_builder.py
│   │   ├── scenario_generator.py
│   │   ├── coverage_intelligence.py
│   │   ├── assertion_validator.py
│   │   ├── selector_validator.py
│   │   ├── test_critic.py
│   │   └── learning_engine.py
│   ├── generators/
│   │   ├── ui_tests.py               # Playwright
│   │   ├── api_tests.py
│   │   ├── security_tests.py         # OWASP-aligned
│   │   ├── accessibility_tests.py    # axe / lighthouse
│   │   ├── performance_tests.py
│   │   └── regression_tests.py
│   ├── executors/
│   │   ├── base.py
│   │   ├── pytest_runner.py
│   │   ├── jest_runner.py
│   │   ├── playwright_runner.py
│   │   ├── maven_runner.py
│   │   ├── gradle_runner.py
│   │   ├── security_runner.py
│   │   └── a11y_runner.py
│   ├── runtime/
│   │   ├── sandbox.py                # workspace isolation
│   │   ├── install_planner.py        # decides what to install
│   │   ├── install_manager.py        # npm/pnpm/pip/maven/gradle
│   │   ├── workspace.py
│   │   └── process_manager.py
│   ├── flaky/
│   │   ├── detector.py
│   │   └── classifier.py
│   ├── healing/
│   │   ├── engine.py
│   │   ├── policies.py
│   │   └── classifiers.py            # selector / timeout / dep / auth / flaky
│   ├── state/
│   │   ├── manager.py
│   │   ├── schemas.py                # pydantic models
│   │   └── migrations.py
│   ├── report/
│   │   ├── builder.py                # builds report-data.json (pure data)
│   │   ├── renderer.py               # HTML render
│   │   └── templates/
│   └── shared/
│       ├── logging.py
│       ├── errors.py
│       ├── paths.py
│       ├── jsonio.py
│       └── git.py
├── prompts/                          # LLM prompt templates (string files)
│   ├── strategy.md
│   ├── scenario.md
│   ├── critic.md
│   └── ...
├── templates/                        # test scaffolding templates
│   ├── playwright/
│   ├── pytest/
│   ├── jest/
│   └── security/
├── configs/
│   ├── defaults.yaml
│   └── language-policies.yaml
├── reports/                          # HTML report template (Jinja)
│   └── enterprise.html.j2
├── pyproject.toml
├── README.md
├── USAGE.md
├── AGENT.md
└── CHANGELOG.md
```

## 4. State files

Stored in `<project>/.qa-agent/`.

| File                          | Owner       | Purpose                                      |
|-------------------------------|-------------|----------------------------------------------|
| `state/project_map.json`      | scanners    | files, languages, frameworks                 |
| `state/dependency_graph.json` | scanners    | per-module imports                           |
| `state/knowledge_graph.json`  | context     | project → module → feature → symbol          |
| `state/risk_matrix.json`      | risk engine | per-flow risk score + rationale              |
| `state/strategy.json`         | strategy    | planned test categories per flow             |
| `state/scenarios.json`        | scenario    | LLM-generated test scenarios                 |
| `state/generated_tests.json`  | generators  | file paths + meta of created tests           |
| `state/critique.json`         | critic      | per-test critique results                    |
| `state/execution_history.json`| executors   | every run, exit codes, durations             |
| `state/installation_history.json` | runtime | every install attempt + outcome              |
| `state/flaky_state.json`      | flaky       | flaky classifications                        |
| `state/coverage_history.json` | report      | feature/risk coverage over time              |
| `state/learnings.json`        | learning    | promoted patterns across runs                |
| `runs/<id>/`                  | orchestrator| per-run artifacts (logs, reports, checkpoints)|

## 5. CLI surface

```
qa-agent full-run [--project PATH] [--categories ui,api,security,...] [--no-llm]
qa-agent analyze [--project PATH]
qa-agent rerun [--project PATH] [--scope flaky|changed|failed|all]
qa-agent report [--project PATH] [--open]
qa-agent state [--project PATH] show|reset
qa-agent version
```

---

## Phase 0 — Foundation ✅

- [x] 0.1 Update `.claude-plugin/plugin.json` with new metadata (version, description, version bump to 2.0.0)
- [x] 0.2 Add `pyproject.toml` (package name `qa_agent`, entry point `qa-agent`)
- [x] 0.3 Add `.gitignore` (Python, node_modules, .qa-agent/, runs/, .venv)
- [x] 0.4 Create `qa_agent/__init__.py` with version constant
- [x] 0.5 Create `qa_agent/shared/` utilities: logging, errors, paths, jsonio, git
- [x] 0.6 Create `qa_agent/state/` — schemas (pydantic), manager (load/save/atomic write), migrations
- [x] 0.7 Create `qa_agent/cli/__main__.py` with `argparse` dispatch
- [x] 0.8 Stub CLI commands: `full_run`, `analyze`, `rerun`, `report`, `state`, `version`
- [x] 0.9 Create `configs/defaults.yaml` + loader in `shared/`
- [x] 0.10 Create root `README.md`, `AGENT.md`, `USAGE.md`, `CHANGELOG.md`

## Phase 1 — Scanning & Context ✅

- [x] 1.1 `scanners/filesystem.py` — walk project, classify files by language, detect ignored paths
- [x] 1.2 `scanners/tech_stack.py` — detect frameworks (Express, FastAPI, Spring, Next.js, Django, NestJS, Flask, etc.) from manifests + signature files
- [x] 1.3 `parsers/python_ast.py` — extract symbols, routes, fixtures from Python files
- [x] 1.4 `parsers/tree_sitter_loader.py` — lazy load grammars for js/ts/python/java
- [x] 1.5 `parsers/ts_morph_bridge.py` — Node helper script (`qa_agent/parsers/_node/ts_morph_extract.js`) invoked via subprocess
- [x] 1.6 `scanners/dependency.py` — parse `package.json`, `pyproject.toml`, `requirements*.txt`, `pom.xml`, `build.gradle*`
- [x] 1.7 `scanners/api_scanner.py` — derive route maps (Express routers, FastAPI routers, Spring `@RestController`, Next.js route handlers)
- [x] 1.8 `scanners/ui_scanner.py` — collect Next.js / Vite / CRA / Vue routes, detect Playwright targets
- [x] 1.9 `context/kg_builder.py` — build hierarchical KG from scanner outputs
- [x] 1.10 `context/summarizer.py` — produce per-module + per-feature text summaries (no LLM)
- [x] 1.11 `context/chunking.py` — split summaries into prompt-safe slices
- [x] 1.12 `context/relevance.py` — given a feature/flow, return relevant module IDs ranked
- [x] 1.13 Wire `qa-agent analyze` to run Phase 1 end-to-end and write all state files
- [x] 1.14 Unit tests for scanners + KG builder against fixture repos (TS+Python)

## Phase 2 — Intelligence (Risk + Strategy)

- [ ] 2.1 `quality/risk_engine.py` — capability detection (auth, payments, mutation flows, permissions, data export, file upload)
- [ ] 2.2 Risk scoring: business impact × state complexity × security exposure × change frequency (from git log)
- [ ] 2.3 Write `state/risk_matrix.json` with per-capability score + rationale
- [ ] 2.4 `quality/strategy_builder.py` — LLM-backed builder that emits planned test categories per capability
- [ ] 2.5 Prompts: `prompts/strategy.md` with strict JSON schema
- [ ] 2.6 Strategy validator: every entry references a real capability, totals within token cap
- [ ] 2.7 Write `state/strategy.json`
- [ ] 2.8 `quality/coverage_intelligence.py` — feature/risk coverage (not line coverage)

## Phase 3 — Test Generation

- [ ] 3.1 `quality/scenario_generator.py` — LLM-backed; emits `scenarios.json` per capability
- [ ] 3.2 `quality/test_critic.py` — LLM critic with rubric (assertions, duplicates, selectors, depth)
- [ ] 3.3 `generators/api_tests.py` — emit pytest/jest API test files from scenarios
- [ ] 3.4 `generators/ui_tests.py` — emit Playwright test files (TS)
- [ ] 3.5 `generators/security_tests.py` — OWASP-aligned (auth, IDOR, injection, CSRF, XSS)
- [ ] 3.6 `generators/accessibility_tests.py` — axe-core via Playwright
- [ ] 3.7 `generators/performance_tests.py` — smoke perf (lighthouse + simple load)
- [ ] 3.8 `generators/regression_tests.py` — flow re-execution based on history
- [ ] 3.9 `quality/assertion_validator.py` — static check: no `expect(true).toBe(true)` / `assert True` / shallow asserts
- [ ] 3.10 `quality/selector_validator.py` — for UI: prefer `data-testid`, reject brittle XPath
- [ ] 3.11 Generation loop: scenario → generate → critique → improve → validate → write

## Phase 4 — Execution

- [ ] 4.1 `runtime/workspace.py` — per-run isolated workspace under `.qa-agent/runs/<id>/`
- [ ] 4.2 `runtime/process_manager.py` — subprocess wrapper with timeout, capture, kill-tree
- [ ] 4.3 `runtime/install_planner.py` — decide what to install based on tech stack
- [ ] 4.4 `runtime/install_manager.py` — pm dispatch (npm/pnpm/pip/poetry/maven/gradle), records to `installation_history.json`
- [ ] 4.5 `executors/base.py` — common Executor interface, result schema
- [ ] 4.6 `executors/pytest_runner.py`
- [ ] 4.7 `executors/jest_runner.py`
- [ ] 4.8 `executors/playwright_runner.py` (browser install handled by install manager)
- [ ] 4.9 `executors/maven_runner.py`
- [ ] 4.10 `executors/gradle_runner.py`
- [ ] 4.11 `executors/security_runner.py` (e.g., zap-baseline, semgrep)
- [ ] 4.12 `executors/a11y_runner.py` (axe via playwright)
- [ ] 4.13 `agent/execution_controller.py` — orchestrates executor selection, batches, retries
- [ ] 4.14 Append `execution_history.json` for every run

## Phase 5 — Quality (Flaky + Self-Healing)

- [ ] 5.1 `flaky/detector.py` — re-run failed/borderline tests N times, classify stability
- [ ] 5.2 `flaky/classifier.py` — timing / network / env / race / order-dependent
- [ ] 5.3 Write `flaky_state.json`
- [ ] 5.4 `healing/classifiers.py` — classify failure (selector / timeout / dep / auth / flaky / assertion)
- [ ] 5.5 `healing/policies.py` — what may be auto-fixed (max retries, allowed mutations)
- [ ] 5.6 `healing/engine.py` — apply bounded fixes; on failure re-run only the affected suite
- [ ] 5.7 `agent/retry_engine.py` — incremental retry driven by `dependency_graph.json` + git diff

## Phase 6 — Reporting

- [ ] 6.1 `report/builder.py` — pure Python; emits `report-data.json` from state files only
- [ ] 6.2 `reports/enterprise.html.j2` — Jinja template: executive summary, risk coverage map, results, screenshots, installation log, flaky table, bugs, recommendations
- [ ] 6.3 `report/renderer.py` — render Jinja to single-file HTML (inline CSS/JS/images as base64)
- [ ] 6.4 Screenshots/video collection from `runs/<id>/artifacts/`
- [ ] 6.5 `qa-agent report --open` opens the latest report

## Phase 7 — Agent + Skills

- [ ] 7.1 `agents/qa-master.md` — single-brain agent (sonnet) with tool list: only the CLI + read state
- [ ] 7.2 `skills/test-orchestrator/SKILL.md` — entry point ("run qa", "צור בדיקות"); shells to `qa-agent full-run`
- [ ] 7.3 `skills/analyze-project/SKILL.md` — runs `qa-agent analyze`
- [ ] 7.4 `skills/rerun/SKILL.md` — runs `qa-agent rerun --scope ...`
- [ ] 7.5 `skills/view-report/SKILL.md` — opens latest HTML report
- [ ] 7.6 Prompt templates wired into Python pipeline (`prompts/*.md` loaded by `qa_agent/quality/*`)
- [ ] 7.7 Bilingual trigger phrases (English + Hebrew)

## Phase 8 — Polish & Validation

- [ ] 8.1 Pytest test suite for `qa_agent/*` (target: scanners, state, strategy, executors)
- [ ] 8.2 End-to-end smoke run against a tiny TS fixture and tiny Python fixture
- [ ] 8.3 `README.md` — install + usage (EN/HE)
- [ ] 8.4 `USAGE.md` — every CLI command + every skill trigger phrase
- [ ] 8.5 `AGENT.md` — trigger phrases reference
- [ ] 8.6 `CHANGELOG.md` — v2.0.0 entry
- [ ] 8.7 Final pass: dead-file check, import linter, no unused deps

---

## Working agreement

- After each task: tick its box in this file, commit, push.
- Branch: `claude/project-overview-jNTHA`.
- One feature per commit where reasonable.
- No task is "done" until its file(s) compile/import cleanly and its state schema (if any) is registered in `qa_agent/state/schemas.py`.
- Open questions for the user go in the **Decisions log** below.

## Decisions log

| Date       | Decision                                       | Notes |
|------------|------------------------------------------------|-------|
| 2026-05-11 | Plugin form (not standalone CLI)               | per user — must install cleanly via Claude Code plugin marketplace |
| 2026-05-11 | Python primary, Node only for Playwright/ts-morph | per user |
| 2026-05-11 | No Docker — local execution only               | per user |
| 2026-05-11 | Drop Go support                                | per user |
