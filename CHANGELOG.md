# Changelog

## [2.0.0] — full rewrite

Single-agent QA Operating System for Claude Code. Replaces v1's
LLM-orchestrated pipeline with a Python engine that owns sequencing,
execution, and reporting; a single `qa-master` agent owns reasoning.

### Phase 0 — Foundation
- Plugin manifest at 2.0.0.
- New Python package `qa_agent` (Python 3.11+).
- Shared utilities: logging, paths, jsonio (atomic), git, config, errors.
- State layer: pydantic schemas + typed StateManager + atomic writes.
- CLI: `qa-agent` console script + 5 subcommands.
- `configs/defaults.yaml`.

### Phase 1 — Scanning & Context
- Filesystem + tech-stack scanners (18 frameworks across TS/JS/Python/Java).
- AST parsers: stdlib `ast` (Python), tree-sitter loader, ts-morph bridge
  via Node subprocess with regex fallback when Node is absent.
- Dependency graph + API + UI scanners (Next.js/Nuxt/Svelte).
- Knowledge graph builder with capability clustering (auth, payments,
  permissions, user-mgmt, data-export, file-upload, search, admin,
  api-public, other).
- Context layer: summarizer, chunking, relevance engine.

### Phase 2 — Intelligence (risk + strategy)
- Risk engine: per-capability scoring on business impact, state
  complexity, security exposure, change frequency (git log).
- Strategy builder: deterministic baseline + `validate_llm_strategy`
  gate that rejects invented capabilities/categories.
- Coverage intelligence: feature/risk coverage (not line coverage).
- `prompts/strategy.md` with strict JSON contract.

### Phase 3 — Test Generation
- 6-category generators (api, ui, security, accessibility, performance,
  regression), language-aware (pytest vs jest, Playwright TS).
- Test critic: assertion validator (bans `expect(true).toBe(true)`,
  `assert True`, empty bodies) + selector validator (rejects XPath,
  deep CSS, framework-hashed classes).
- Generation loop: scenarios -> generate -> critique -> validate -> write.
- `prompts/scenario.md`, `prompts/critic.md`.

### Phase 4 — Execution
- Process manager: timeout + kill-tree (process group), 256 KB tail.
- Workspace: per-run dir at `.qa-agent/runs/<id>/`.
- Install planner + install manager (pip/poetry/npm/pnpm/yarn) with
  every attempt recorded to `installation_history.json`.
- Executors: pytest, jest (--json), playwright (json reporter), maven
  Surefire, gradle, plus security + a11y wrappers.
- Execution controller: groups tests, dispatches, appends history.

### Phase 5 — Quality (flaky + self-healing + retry)
- Flaky detector: re-runs failed files N times, classifies cause.
- Self-healing engine: bounded conservative fixes (`add-wait`,
  `increase-timeout`); never weakens assertions.
- Retry engine: `--scope all|failed|flaky|changed` driven by git diff +
  dependency graph.

### Phase 6 — Reporting
- `report/builder.py`: pure-Python data from state. Quality score
  deterministic — no LLM path.
- `reports/enterprise.html.j2`: executive summary, risk coverage map,
  strategy, per-category results, flaky table, critique findings,
  installation log.

### Phase 7 — Agent + Skills
- Single `qa-master.md` agent (sonnet) with Bash + Read only.
- 4 skills: test-orchestrator, analyze-project, rerun, view-report.
- Bilingual EN + HE trigger phrases in every skill description.
- `agent/lifecycle.py` + `agent/planner.py`: phase enum + dry-runnable
  RunPlan helpers.

### Phase 8 — Polish
- E2E smoke test (no-llm pipeline + report rendering) against a tiny
  FastAPI fixture.
- README / USAGE / AGENT / CHANGELOG updated to v2 final.
- 51 tests passing.
