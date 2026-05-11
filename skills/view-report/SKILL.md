---
name: view-report
description: Open the latest QA HTML report. Triggers on "open qa report", "show qa report", "where is the report", "פתח דוח qa", "הצג דוח qa".
---

# view-report

The user wants to see the report from the most recent run.

## Hand off

> Run `qa-agent report --open --project "${PWD}"`. The CLI prints the
> absolute path to the report file on stdout — surface that exact path
> in your reply so the user can click it.

## If there's no run yet

If `${PWD}/.qa-agent/runs/` is empty or missing, tell the user to run
**test-orchestrator** first.
