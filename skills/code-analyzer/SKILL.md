---
name: code-analyzer
description: >
  Internal shared skill — scans a codebase and produces structured JSON metadata. Standalone
  entry point — delegates to qa-code-analyzer agent.

  Standalone use: "map my project structure", "show me all endpoints", "what does this codebase contain",
  "analyze my code structure", "list all API routes". Hebrew (עברית): "מפה את מבנה הפרויקט",
  "הצג את כל ה-endpoints", "מה יש בקוד הזה", "נתח את מבנה הקוד", "רשום את כל ה-routes".
---

# code-analyzer (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-code-analyzer` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Generate a `run_id` (uuid).
4. Invoke `qa-skills:qa-code-analyzer` agent with:
   ```json
   {
     "run_id": "...",
     "project_root": "...",
     "analysis_path": "${project_root}/.qa-skills/logs/${run_id}/analysis.json",
     "locale": "he|en"
   }
   ```
5. Display the agent's small summary (counts, language detected). Mention where the full analysis JSON was written.

The agent owns scanning, classification, and JSON output.
