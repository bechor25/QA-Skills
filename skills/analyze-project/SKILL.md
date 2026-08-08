---
name: analyze-project
description: Scans and risk-rates the current project without generating or running any tests. Use when the user says "analyze project", "scan project", "what does my project contain", "נתח פרויקט", "סרוק פרויקט".
---

# analyze-project

The user wants understanding, not execution.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" analyze --project "${PROJECT_ROOT}"
```

Then summarize:

- `project_summary` (one paragraph)
- top 3 risk capabilities with their score + rationale
- frameworks detected

Do not run any tests and do not install anything, because this skill is read-only by
contract — users invoke it precisely when they are not ready to execute.

## What to surface back

- Frameworks detected (from `state/project_map.json`)
- Top 3 risk entries (from `state/risk_matrix.json`, sorted by `score`)
- Coverage gaps if any (categories planned in `state/strategy.json` that
  have no executed runs yet in `state/execution_history.json`)
