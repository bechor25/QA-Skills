---
name: test-orchestrator
description: Entry point for a full QA run. Triggers on "run qa", "qa run", "full qa run", "generate tests", "generate tests for my project", "הרץ qa", "הרץ בדיקות", "צור בדיקות", "צור בדיקות לפרויקט שלי". Hands off to the qa-master agent which invokes the qa-skills-run wrapper and surfaces the HTML report.
---

# test-orchestrator

The user wants a full QA run. Hand off to the **qa-master** agent.

## What to do

1. Resolve the project root (see qa-master's "Project root resolution"
   section). Confirm with the user if ambiguous.
2. Invoke the qa-master agent with the instruction:
   > Run a full QA pipeline against `${PROJECT_ROOT}`. Use
   > `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run full-run`. When complete,
   > surface the report path and the top 3 risks.
3. After the agent finishes, ensure the user sees:
   - Quality score (0–100)
   - Pass rate (%)
   - Path to the HTML report
   - Top 3 capabilities by risk

## Hard constraints

- Do **not** run `pytest`, `npm`, `pip`, or `playwright` directly from this
  skill — go through the agent so all installs and runs are recorded in
  `installation_history.json` / `execution_history.json`.
- Do **not** invoke `qa-agent` directly; always go through
  `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run` so the plugin venv bootstrap
  fires on first call.
- Do **not** invent quality numbers. The HTML report is the verdict.

## First-run latency

The very first `qa-skills-run` call after install creates a Python venv
under `${CLAUDE_PLUGIN_ROOT}/.venv` and installs the `qa-agent` package
(~20-40 s). Subsequent calls reuse the venv and start instantly.

## Notes

The qa-master agent reads state from `${PROJECT_ROOT}/.qa-agent/state/`
and writes the HTML report at
`${PROJECT_ROOT}/.qa-agent/runs/<latest>/report.html`.
