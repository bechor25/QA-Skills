---
name: unit-test
description: >
  Generate unit tests for code modules — functions, classes, services. Standalone entry
  point — delegates to qa-unit-test agent.

  English triggers (standalone): "write unit tests for [file]", "test this function",
  "add unit tests to [module]", "improve test coverage for [path]", "find edge cases in [file]".

  Hebrew triggers (עברית): "כתוב בדיקות יחידה ל-[קובץ]", "בדוק את הפונקציה הזאת",
  "הוסף בדיקות יחידה ל-[מודול]", "שפר כיסוי בדיקות", "מצא מקרי קצה ב-[קובץ]".

  Supports TypeScript/Jest/Vitest, Python/pytest, Java/JUnit 5, C#/NUnit.
---

# unit-test (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-unit-test` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root` and (optional) target module path from user message.
3. If a single file is targeted → invoke `qa-skills:qa-code-analyzer` first on that file only, pass slice to agent.
4. Else invoke `qa-skills:qa-code-analyzer` on full project, then pass module list.
5. Invoke `qa-skills:qa-unit-test` agent with:
   ```json
   {
     "project_root": "...",
     "language": "...",
     "modules": [...],
     "locale": "he|en",
     "budgets": {"max_tokens": 80000, "max_seconds": 600}
   }
   ```
6. Display agent summary: tests written, tests passing, files updated.

The agent owns framework detection, generation, execution, and fix loop.
