---
name: api-test
description: >
  Generate API/HTTP tests for REST endpoints, GraphQL, or any HTTP interface. Standalone
  entry point — delegates to qa-api-test agent.

  English triggers (standalone): "test my API", "test the endpoints", "check auth flows",
  "validate API responses", "write API tests", "test my REST API", "test HTTP endpoints".

  Hebrew triggers (עברית): "בדוק את ה-API שלי", "בדיקות API", "בדוק את ה-endpoints שלי",
  "כתוב בדיקות API", "בדוק תשובות HTTP", "בדיקות REST", "בדוק נקודות קצה".

  Supports: httpx (Python), supertest (Node.js), RestAssured (Java), HttpClient (C#).
---

# api-test (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-api-test` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Invoke `qa-skills:qa-code-analyzer` to get routes.
4. Detect API server URL from project config (uvicorn port, spring boot port, package.json scripts). Default `http://localhost:8000`.
5. Invoke `qa-skills:qa-api-test` agent with:
   ```json
   {
     "project_root": "...",
     "language": "...",
     "routes": [...],
     "modules": [...],
     "locale": "he|en",
     "preflight": {
       "server_check_url": "<detected>",
       "abort_if_no_server": true
     },
     "budgets": {"max_tokens": 80000, "max_seconds": 600}
   }
   ```
6. Display agent summary.

The agent owns pre-flight, generation, execution, fix loop.
