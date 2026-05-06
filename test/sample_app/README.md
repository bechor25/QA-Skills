# Sample QA App

Dummy FastAPI project for exercising **QA-Skills** end-to-end. Has every
surface the skills look for:

| Surface | Where | Skill that targets it |
|---|---|---|
| Pure functions | `app/calc.py` | `unit-test` |
| Auth helpers (bcrypt + JWT) | `app/auth.py` | `unit-test`, `security-test` |
| User store (in-memory CRUD) | `app/users.py` | `unit-test` |
| HTTP routes | `app/routes.py` | `api-test`, `security-test` |
| OpenAPI spec | `GET /openapi.json` | `contract-test` |
| HTML pages w/ forms | `app/templates/*.html` | `ui-playwright`, `accessibility-test` |
| Static assets | `app/static/styles.css` | `accessibility-test` |
| Existing pytest baseline | `tests/test_smoke.py` | `flaky-detector`, `env-validator` |

## Quickstart

```bash
cd test/sample_app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the app (needed for ui/api/a11y/contract skills to hit a live server)
uvicorn app.main:app --reload --port 8001

# In a separate shell, baseline test run
pytest -q
```

## Demo users seeded on startup

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `admin1234` | admin |
| `alice@example.com` | `alice1234` | user |

## Running QA-Skills against this project

From a Claude Code session inside `test/sample_app/`:

```
generate tests for my project
```

or in Hebrew:

```
צור בדיקות לפרויקט שלי
```

The orchestrator will:

1. Run `env-validator` (checks Python + pytest + uvicorn).
2. Run `code-analyzer` to map modules + routes.
3. Dispatch `unit-test`, `api-test`, `contract-test`, `security-test`,
   `ui-playwright`, `accessibility-test` against their respective surfaces.
4. Run `flaky-detector` (3× re-run).
5. Aggregate via `coverage-reporter` and open the `html-reporter` output.

## Intentional weak spots

`app/auth.py::decode_token_unsafe` exists as a known target for
`security-test` (accepts unsigned tokens). The production endpoints do
**not** use it. Other endpoints are reasonably hardened — the security
skill should report a clean bill on those.
