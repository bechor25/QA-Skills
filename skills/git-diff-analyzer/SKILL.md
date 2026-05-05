---
name: git-diff-analyzer
description: >
  Internal skill — classifies per-module change severity using git diff. Standalone entry
  point — delegates to qa-git-diff-analyzer agent.

  Standalone use: "what changed in my code since last commit", "show me semantic changes".
  Hebrew: "מה השתנה בקוד שלי", "הצג שינויים משמעותיים מאז הcommit האחרון".
---

# git-diff-analyzer (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-git-diff-analyzer` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Generate `run_id`.
4. Run code-analyzer first (to produce `analysis.json`), then invoke `qa-skills:qa-git-diff-analyzer` agent with:
   ```json
   {
     "run_id": "...",
     "project_root": "...",
     "analysis_path": "${project_root}/.qa-skills/logs/${run_id}/analysis.json",
     "language": "...",
     "locale": "he|en"
   }
   ```
5. Display per-class counts (unchanged / trivial / body_changed / signature_changed / unknown).

The agent owns diff parsing and classification.
