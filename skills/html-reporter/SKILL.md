---
name: html-reporter
description: >
  Internal shared skill — generates a self-contained HTML report from report-data.json and
  opens it in the browser. Standalone entry point — delegates to qa-html-reporter agent.

  Standalone use: "show me the coverage report", "open test report", "regenerate the HTML report",
  "reopen the report". Hebrew: "פתח את דוח הבדיקות", "הצג את הדוח", "צור את ה-HTML report".
---

# html-reporter (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-html-reporter` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Locate `${project_root}/test-reports/report-data.json` (latest).
4. Invoke `qa-skills:qa-html-reporter` agent with:
   ```json
   {
     "project_root": "...",
     "report_data_path": "...",
     "locale": "he|en"
   }
   ```
5. Display HTML report path and confirm browser opened.

The agent owns HTML generation and self-contained packaging.
