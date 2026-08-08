---
name: view-report
description: Opens the latest QA HTML report in the browser and prints its path. Use when the user says "open qa report", "show qa report", "where is the report", "פתח דוח qa", "הצג דוח qa".
---

# view-report

The user wants to see the report from the most recent run.

## Hand off

> Run `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run report --open --project "${PROJECT_ROOT}"`. The CLI prints the
> absolute path to the report file on stdout — surface that exact path
> in your reply so the user can click it.

## If there's no run yet

If `${PROJECT_ROOT}/.qa-agent/runs/` is empty or missing, tell the user to run
**test-orchestrator** first.
