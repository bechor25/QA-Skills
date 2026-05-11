---
name: analyze-project
description: Scan + risk-rate the project without generating or running tests. Triggers on "analyze project", "scan project", "what does my project contain", "נתח פרויקט", "סרוק פרויקט".
---

# analyze-project

The user wants understanding, not execution. Hand off to **qa-master** with:

> Run `qa-agent analyze --project "${PWD}"`. Then summarize:
> - project_summary (one paragraph)
> - top 3 risk capabilities with their score + rationale
> - frameworks detected
>
> Do not run any tests, do not install anything.

## What to surface back

- Frameworks detected (from `state/project_map.json`)
- Top 3 risk entries (from `state/risk_matrix.json`, sorted by `score`)
- Coverage gaps if any (categories planned in `state/strategy.json` that
  have no executed runs yet in `state/execution_history.json`)
