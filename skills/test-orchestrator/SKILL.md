---
name: test-orchestrator
description: Entry point for a full QA run. Triggers on "run qa", "qa run", "full qa run", "generate tests", "generate tests for my project", "הרץ qa", "הרץ בדיקות", "צור בדיקות", "צור בדיקות לפרויקט שלי". Invokes the QA Master agent which runs `qa-agent full-run` and surfaces the HTML report.
---

# test-orchestrator

The user wants a full QA run. Hand off to the **qa-master** agent.

## What to do

1. Confirm the project root with the user if it's ambiguous; default to `$PWD`.
2. Invoke the qa-master agent with the instruction:
   > Run a full QA pipeline against `${PWD}`. Use `qa-agent full-run`. When
   > complete, surface the report path and the top 3 risks.
3. After the agent finishes, ensure the user sees:
   - Quality score (0–100)
   - Pass rate (%)
   - Path to the HTML report
   - Top 3 capabilities by risk

## Hard constraints

- Do **not** run `pytest`, `npm`, `pip`, or `playwright` directly from this
  skill — go through the agent so all installs and runs are recorded in
  `installation_history.json` / `execution_history.json`.
- Do **not** invent quality numbers. The HTML report is the verdict.

## Notes

The qa-master agent reads state from `${PWD}/.qa-agent/state/` and writes
the HTML report at `${PWD}/.qa-agent/runs/<latest>/report.html`.
