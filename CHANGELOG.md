# Changelog

## v2.0.0 — 2026-05-11

**BREAKING — pipeline rewritten as Python-driven.** The orchestrator is no
longer an 880-line LLM blueprint; it is a 100-line Bash wrapper around the
new driver `scripts/qa_run.py`. Every phase that previously depended on the
LLM choosing to call a Bash gate is now a direct Python call. There is no
path to fake-green reports or skipped execution.

### Why

The v1 run on real projects produced `report-data.json` in v1 shape with
`quality_score: 88` despite no tests being executed and every "HARD GATE"
in the agent MDs being silently skipped by the LLM. The diagnostic in
[ARCHITECTURE_DIAGNOSTIC.md](ARCHITECTURE_DIAGNOSTIC.md) explains why
MD-as-program does not scale to large projects.

### Added

- `scripts/qa_run.py` — top-level pipeline driver. Owns phases
  0/1/2/2.7/3/5/5.5/6/7/8/8b/9.
- `qa_skills/driver.py` — `task_subprocess`, `verify_on_disk`,
  `retry_once`, `build_run_context`, `write_checkpoint`.
- `qa_skills/prompt_builder.py` — per-file sub-agent prompts capped at
  4096 chars. One file per Task call.
- `qa_skills/learnings.persist_learnings(...)` — Python implementation of
  Phase 5.5 (vuln_patterns + flaky_history + category_effectiveness).
- 92 new pytest tests: `test_driver.py`, `test_prompt_builder.py`,
  `test_qa_run.py` (end-to-end), `test_learnings.py` (+8 persist tests).

### Changed (BREAKING)

- `agents/qa-orchestrator.md`: **880 → 104 lines**. Invokes `qa_run.py`
  via `Bash` and returns its stdout verbatim. No `Task` calls.
- `agents/qa-{unit,api,security,contract}-test.md`: ~250 → ~130 lines
  each. Receive one `expected_file` per Task call. No phase numbering, no
  Bash gates, no batching, no execution. Driver handles all of that.
- `agents/qa-{ui,a11y}-test.md`: 514 / 281 → 117 / 111 lines. `server_plan`
  pre-resolved by driver; sub-agent never probes for a server.
- `agents/qa-domain-analyzer.md`: now driver-centric (`chunk_path` input,
  read-only side effect, no banners).

### Removed

- `agents/qa-coverage-reporter.md` — replaced by direct Python call to
  `scripts/build_report.py` from the driver.
- `skills/coverage-reporter/SKILL.md` and the `skills/coverage-reporter/`
  directory.
- `RUNTIME_ENFORCEMENT_PLAN.md`, `STUB_FIX_PLAN.md` — superseded by
  `ARCHITECTURE_DIAGNOSTIC.md` + `IMPLEMENTATION_PLAN.md`.

### Eliminated failure modes

| Symptom in v1                              | Eliminated by                                            |
|--------------------------------------------|----------------------------------------------------------|
| `agent_output_*.json` missing              | Driver writes after every sub-agent return.              |
| `execution_*.json` missing (tests not run) | Driver invokes `runner.run_tests()` itself per batch.    |
| `domain_brief_*.json` missing              | Driver iterates planned cats in Phase 2.7; not optional. |
| `report-data.json` v1 shape                | qa-coverage-reporter deleted; driver calls `build_report.py` directly. |
| "Generate all remaining" prompt overflow   | One file per Task call. Prompt capped at 4096 chars.     |
| Fake `quality_score: 88`                   | Score comes from `qa_skills.quality.compute_quality_score` only. |
| Boilerplate "401 without auth" × 30 files  | Each sub-agent sees its own `domain_brief` hints slice.  |
| Skipped batching → context overflow        | Batching enforced by Python; `batch_state.json` for resume. |

### Stats

- MD total across all agents: **3,986 → 1,005 lines** (~75% reduction).
- pytest: 145 → **337 green** (+192 new tests).
- New Python LOC: ~1,150 (driver + prompt_builder + learnings.persist + tests).
