---
name: env-validator
description: >
  Internal skill — validates environment readiness before any test generation begins. Standalone
  entry point — delegates to qa-env-validator agent.

  English triggers (standalone): "check my environment", "validate setup", "is my project ready for tests".
  Hebrew triggers (עברית): "בדוק את הסביבה שלי", "האם הפרויקט מוכן לבדיקות", "בדוק הגדרות".
---

# env-validator (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-env-validator` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Detect language from project files.
4. Invoke `qa-skills:qa-env-validator` agent with:
   ```json
   {
     "project_root": "...",
     "language": "...",
     "categories_enabled": ["unit", "api", "ui", "security", "a11y", "contract"],
     "checkpoint_dir": "${project_root}/.qa-skills/checkpoints",
     "locale": "he|en"
   }
   ```
5. Display checks pass/fail and `categories_remaining`.

The agent owns toolchain and dependency checks.
