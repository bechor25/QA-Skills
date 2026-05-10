---
name: ui-playwright
description: >
  Generate E2E browser tests using Playwright for frontend applications.
  Standalone entry point — delegates all work to the qa-ui-test agent.

  English triggers (standalone): "write UI tests", "test my frontend", "E2E tests",
  "Playwright tests", "test the login flow", "browser tests", "test user flows",
  "test the UI", "write end-to-end tests".

  Hebrew triggers (עברית): "כתוב בדיקות UI", "בדוק את הממשק שלי", "בדיקות E2E",
  "בדיקות Playwright", "בדוק את זרימת הלוגין", "בדיקות דפדפן", "בדוק זרימות משתמש",
  "בדיקות ממשק גרפי", "בדיקות end-to-end".
---

# ui-playwright (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-ui-test` agent.

## Behavior

1. Detect locale (Hebrew chars → `he`, else `en`).
2. Resolve `project_root`. Ask once if missing.
3. **Pre-step — env-validator:** invoke `qa-skills:qa-env-validator` with `{categories_enabled: ["ui"], auto_install: true}`. This installs Playwright + browser if missing and surfaces `installs_performed[]`. If `ui` ends up in `categories_removed[]` → abort with the env-validator's reason (e.g., `unsupported_language`). qa-ui-test no longer installs anything itself — env-validator is the single source for installs.
4. Detect dev server URL from `package.json` scripts (next dev → 3000, vite → 5173). Default `http://localhost:3000`.
5. Invoke `qa-skills:qa-ui-test` agent with:
   ```json
   {
     "project_root": "...",
     "locale": "he|en",
     "preflight": {
       "server_check_url": "<detected>",
       "abort_if_no_server": true,
       "smoke_first": true
     },
     "budgets": {"max_tokens": 70000, "max_seconds": 600}
   }
   ```
6. Display agent's `status`, batches completed/skipped, tests passing counts. If env-validator's `installs_performed[]` non-empty → prefix with `📦 הותקן אוטומטית: <list>` (he) / `📦 Auto-installed: <list>` (en) so user knows env was modified.

The agent owns pre-flight, reconnaissance, smoke-first batching, and fix loops.
