# Copilot instructions — qa-skills

## Overview

This repository is **itself a Claude Code plugin** (`qa-skills`), not an app under test. It
ships skills and LLM sub-agents that drive a Python engine (`qa-agent`) to scan a *target*
project, generate tests, run them, triage failures, heal them, and emit an HTML report. The
target project is always some other codebase — never this repo, so never point the pipeline
at this working directory.

## Tech stack

Python ≥ 3.11, Pydantic v2 (state models), PyYAML (config), Jinja2 (HTML report), Rich (CLI
output), optional tree-sitter for parsing, pytest ≥ 8 for tests, setuptools packaging with a
`qa-agent` console script. The engine drives pytest / jest / vitest / playwright / maven /
gradle inside target projects. Supported target languages: TypeScript/JavaScript, Python,
Java.

## Structure

- `qa_agent/` — the engine: `scanners/` → `parsers/` → `context/` → `quality/` →
  `generators/` → `runtime/` → `executors/` → `flaky/` + `healing/` → `report/`.
- `qa_agent/state/` — Pydantic schemas + `manager.py`, the only supported state I/O path.
- `qa_agent/cli/commands/` — deterministic pipeline phases (no LLM).
- `skills/` and `agents/` — the Markdown skill/sub-agent layer shipped to users.
- `bin/`, `scripts/`, `configs/`, `reports/` — wrapper, setup, defaults, report template.

## Setup, build, test

```bash
scripts/setup.sh                  # bootstrap venv + editable install
pip install -e '.[parsing,dev]'   # manual equivalent
python -m build                   # build the package
pytest qa_agent/tests             # full suite — the only verification gate
```

## Verification loop

Run `pytest qa_agent/tests` after every change and keep iterating until the suite passes,
because the shared state schemas mean a local-looking edit usually breaks a downstream
phase. When you claim something is fixed, show the pytest output as evidence instead of
asserting success.

## Guidelines

- Route all state reads/writes through `qa_agent/state/manager.py`, because it owns atomic
  writes and schema validation; direct JSON access silently corrupts later phases.
- Keep `qa_agent/cli/commands/*` free of LLM calls, so every deterministic phase stays
  reproducible and unit-testable.
- Resolve plugin asset paths through `${CLAUDE_PLUGIN_ROOT}`, since the plugin is installed
  outside the user's project.
- Keep skill frontmatter under ~100 tokens and bodies under ~5000 tokens; move detail into
  `skills/<name>/references/*.md` so the always-loaded surface stays small.
- Skills are bilingual (English + Hebrew triggers) — update both languages together.
- `scaffold` overwrites test files and wipes authored bodies; treat it as destructive.
- The HTML report and `report-data.json` are the authoritative verdict — never restate
  quality scores with different numbers.

More detail: `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md`, and the path-scoped rules under
`.github/instructions/`.
