---
name: flaky-detector
description: >
  Internal skill — detects non-deterministic (flaky) tests by re-running the suite 3 times.
  Standalone entry point — delegates to qa-flaky-detector agent.

  Standalone use: "find flaky tests", "check for unstable tests", "which tests are unreliable".
  Hebrew: "מצא בדיקות לא יציבות", "בדוק אילו בדיקות לא אמינות", "בדיקות לא דטרמיניסטיות".
---

# flaky-detector (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-flaky-detector` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root` and detect language.
3. Discover test files (look in `tests/`, `test/`, `__tests__/`).
4. Invoke `qa-skills:qa-flaky-detector` agent with:
   ```json
   {
     "project_root": "...",
     "language": "...",
     "test_outputs": [/* discovered test files */],
     "locale": "he|en",
     "budgets": {"max_seconds": 600}
   }
   ```
5. Display flaky test list with cause hypothesis and fix suggestion. If none → "no flaky tests detected".

The agent owns the 3-run loop and analysis.
