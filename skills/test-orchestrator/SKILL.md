---
name: test-orchestrator
description: >
  Central QA orchestrator — automatically generates, runs, and reports a full test suite
  for any codebase. SINGLE ENTRY POINT for all QA activities. Trigger this skill for any
  test-related request, regardless of how the user phrases it.

  English triggers: "generate tests", "write tests", "write tests for", "run tests",
  "test my code", "what's my test coverage", "what am I missing in tests", "update tests",
  "scan my code for tests", "check test quality", "test coverage analysis", "create tests",
  "build test suite", "I need tests", "check what's untested".

  Hebrew triggers (טריגרים בעברית): "צור בדיקות", "כתוב בדיקות", "הרץ בדיקות",
  "בנה בדיקות", "יצירת בדיקות", "מה הכיסוי שלי", "מה לא נבדק", "עדכן בדיקות",
  "סרוק את הקוד לבדיקות", "בדוק את הפרויקט שלי", "ניתוח כיסוי בדיקות",
  "אני רוצה בדיקות", "צריך בדיקות", "תייצר בדיקות", "תכתוב בדיקות",
  "תרוץ בדיקות", "מה לא נבדק בקוד".

  Requires only: project path. Output: HTML report opened in browser.
---

# test-orchestrator (entry point)

Thin trigger skill. All work is delegated to the `qa-skills:qa-orchestrator` agent.

## Behavior

1. Detect locale from the user's message (Hebrew chars → `he`, else `en`).
2. Resolve `project_path` from the user's message. If absent, ask the user once.
3. Parse optional flags from the message:
   - `--interactive` → strategy phase pauses for confirmation (default: auto).
   - `--force-full` → ignore state, regenerate all.
   - `--categories=unit,api,...` → restrict generated categories.
4. **Emit entry banner** as plain text BEFORE invoking the orchestrator:
   - en: `🤖 qa-skills | starting QA flow on {project_path}...`
   - he: `🤖 qa-skills | מפעיל QA על {project_path}...`
5. Invoke the `qa-skills:qa-orchestrator` agent via the Task tool with:
   ```json
   {
     "project_path": "<resolved>",
     "locale": "he|en",
     "force_full": <bool>,
     "categories": <list|null>,
     "mode": "auto|interactive",
     "interactive": <bool>
   }
   ```
6. Display the agent's final summary to the user. Do not echo intermediate work.
7. Open the HTML report path returned by the agent.
8. **Emit exit banner** as plain text AFTER orchestrator returns:
   - en: `🤖 qa-skills | done | quality {score}/100 | report: {report_path}`
   - he: `🤖 qa-skills | סיום | איכות {score}/100 | דוח: {report_path}`

## What you do NOT do here

- Do not generate tests yourself.
- Do not read individual test files.
- Do not invoke sub-agents directly — only the orchestrator agent.
- Do not load the orchestrator's full system prompt into your context.

The agent owns all real work. You are the trigger surface.
