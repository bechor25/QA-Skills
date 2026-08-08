# AGENTS.md

Cross-tool entry point for coding agents (GitHub Copilot, Claude Code, Gemini, Codex).
Claude Code users: `CLAUDE.md` is the fuller version of this file — read it too.

## Overview

`qa-skills` is **itself a Claude Code plugin**, not an application under test. It ships
skills + LLM sub-agents that drive a Python engine (`qa-agent`) to scan a *target* project,
generate tests, execute them, triage failures, heal them, and emit an HTML report. The
target project is always another codebase — never this repo, so never run the pipeline
against this working directory.

## Tech stack

Python ≥ 3.11 · Pydantic v2 · PyYAML · Jinja2 · Rich · tree-sitter (optional `parsing`
extra) · pytest ≥ 8 · setuptools. Target-project runners driven by the engine: pytest, jest,
vitest, playwright, maven, gradle. Supported target languages: TypeScript/JavaScript,
Python, Java.

## Structure

```
qa_agent/     Python engine (scanners → parsers → context → quality → generators →
              runtime → executors → flaky/healing → report), plus state/ and tests/
skills/       user-facing skills (SKILL.md + references/)
agents/       plugin sub-agents shipped to users
bin/          qa-skills-run wrapper + venv bootstrap
configs/      defaults.yaml
scripts/      setup.sh + agent hooks
.claude/      agents, commands, rules, hook settings for working ON this repo
.github/      copilot instructions, path-scoped instructions, prompts, CI
```

## Setup, build, test

```bash
scripts/setup.sh                  # bootstrap venv + editable install (parsing,dev extras)
pip install -e '.[parsing,dev]'   # equivalent manual install
python -m build                   # build the distributable package
pytest qa_agent/tests             # the entire verification gate
```

## Verification loop (required)

Run `pytest qa_agent/tests` after every change and iterate until it is green, because the
Pydantic state schemas are shared across ~15 modules and a local-looking rename usually
breaks a downstream phase. When you claim a change works, paste the pytest summary output as
evidence rather than asserting it.

## Guidelines

- State under `<target>/.qa-agent/state/` is the contract between phases. Read/write it only
  through `qa_agent/state/manager.py`, because that module owns atomic writes and schema
  validation.
- Keep LLM work in `agents/*.md` and deterministic work in `qa_agent/cli/commands/*`, so
  every pipeline phase stays reproducible without a model in the loop.
- Resolve plugin asset paths through `${CLAUDE_PLUGIN_ROOT}`, since the plugin lives outside
  the user's project.
- Keep skill frontmatter under ~100 tokens and skill bodies under ~5000 tokens; push detail
  into `skills/<name>/references/*.md`.
- Re-running `scaffold` overwrites test files and wipes authored bodies — treat it as
  destructive.

## Trigger phrases

Skills are bilingual. Keep English and Hebrew triggers in sync when editing a description,
otherwise Hebrew-speaking users lose the trigger entirely.

| Skill | English | Hebrew |
|---|---|---|
| `test-orchestrator` | `run qa` / `qa run` / `full qa run` / `generate tests` | `הרץ qa` / `הרץ בדיקות` / `צור בדיקות` |
| `test-fixer` | `heal tests` / `fix the tests` / `improve test quality` | `תקן בדיקות` / `שפר איכות בדיקות` |
| `analyze-project` | `analyze project` / `scan project` | `נתח פרויקט` / `סרוק פרויקט` |
| `rerun` | `rerun tests` / `rerun failed` | `הרץ שוב` / `הרץ נכשלים` |
| `view-report` | `open qa report` / `show qa report` | `פתח דוח qa` / `הצג דוח qa` |

`test-orchestrator` is the top-level entry point; it drives `qa-agent` CLI commands and fans
out LLM sub-agents for the scoped authoring phases. `test-fixer` is a second top-level entry
point that runs **after** a completed `test-orchestrator` run, driving the heal loop
(`heal-diagnose` / `heal-apply` / `heal-rerun` / `heal-status`) with the
`qa-ops-diagnostician` (shared fixes) and `qa-test-fixer` (per-test residue) sub-agents.

## Resources

`ARCHITECTURE.md` (layer map) · `CLAUDE.md` (full agent guide) · `USAGE.md` · `INSTALL.md` ·
`.claude/rules/` and `.github/instructions/` (path-scoped rules).
