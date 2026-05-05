---
name: contract-test
description: >
  Generate contract tests verifying API responses match OpenAPI/Swagger schema or golden masters.
  Standalone entry point — delegates to qa-contract-test agent.

  English triggers (standalone): "contract test", "OpenAPI test", "schema test", "API schema validation",
  "check if API matches spec", "validate API contract", "test schema conformance".

  Hebrew triggers (עברית): "בדיקות חוזה", "בדיקות OpenAPI", "בדיקות schema", "בדוק ה-API מול המפרט",
  "אמת את החוזה", "בדיקות schema validation", "בדוק סכמת תגובות".
---

# contract-test (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-contract-test` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Invoke `qa-skills:qa-code-analyzer` for routes.
4. Detect API server URL.
5. Invoke `qa-skills:qa-contract-test` agent with:
   ```json
   {
     "project_root": "...",
     "language": "...",
     "routes": [...],
     "locale": "he|en",
     "preflight": {"server_check_url": "<detected>", "abort_if_no_server": true},
     "budgets": {"max_tokens": 60000, "max_seconds": 480}
   }
   ```
6. Display agent summary + the chosen `mode` (openapi / golden_capture / golden_update).

The agent owns mode detection, schema validation, and golden master capture.
