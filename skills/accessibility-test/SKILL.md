---
name: accessibility-test
description: >
  Generate WCAG 2.1 AA accessibility tests using Playwright + axe-core. Standalone entry
  point — delegates to qa-a11y-test agent.

  English triggers (standalone): "test accessibility", "WCAG", "a11y", "check accessibility",
  "aria tests", "screen reader", "keyboard navigation tests", "check WCAG compliance".

  Hebrew triggers (עברית): "בדוק נגישות", "בדיקות נגישות", "WCAG", "בדוק מקלדת",
  "בדיקות קוראי מסך", "נגישות WCAG", "a11y", "בדוק ניגוד צבעים".
---

# accessibility-test (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-a11y-test` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. **Pre-step — env-validator:** invoke `qa-skills:qa-env-validator` with `{categories_enabled: ["a11y"], auto_install: true}`. Installs Playwright + axe-core/playwright if missing. Abort if `a11y` removed.
4. Invoke `qa-skills:qa-code-analyzer` to get frontend_files + routes.
5. Detect frontend dev server URL.
6. Invoke `qa-skills:qa-a11y-test` agent with:
   ```json
   {
     "project_root": "...",
     "frontend_files": [...],
     "routes": [...],
     "locale": "he|en",
     "preflight": {"server_check_url": "<detected>", "abort_if_no_server": true},
     "budgets": {"max_tokens": 60000, "max_seconds": 480}
   }
   ```
7. Display agent summary including violations counts. Surface `installs_performed[]` if non-empty.

The agent owns axe-core integration and WCAG check generation.
