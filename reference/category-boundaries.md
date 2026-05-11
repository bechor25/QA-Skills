# Category Boundaries

Each test category owns a specific universe and produces a specific kind of test. Sub-agents must respect these boundaries. The orchestrator's `qa_skills.path_planner` and `qa_skills.coverage` enforce them deterministically.

---

## Universe (denominator) per category

| Category   | Universe                                                                     | Example item                |
|------------|------------------------------------------------------------------------------|-----------------------------|
| `unit`     | `analysis.modules` where `type != "frontend"`                                | `app/auth.py`               |
| `api`      | `analysis.routes` where `kind == "api"`                                      | `POST /api/login`           |
| `contract` | same as api                                                                  | `GET /api/users/{id}`       |
| `security` | same as api                                                                  | `POST /api/register`        |
| `ui`       | `analysis.frontend_files` where `kind` ∈ {page, ssr_template, spa_component, static_html} | `templates/login.html` |
| `a11y`     | same as ui                                                                   | `templates/login.html`      |

The orchestrator's `compute_expected_files()` (in `qa_skills.path_planner`) reads from these universes only. A category's sub-agent receives only its slice — never another category's universe.

---

## What each agent owns

| Agent              | Generates                                                | Does NOT generate                          |
|--------------------|----------------------------------------------------------|--------------------------------------------|
| `qa-unit-test`     | function-level tests of pure logic, mocked dependencies  | HTTP calls, real DB, browser, axe, schema  |
| `qa-api-test`      | HTTP-level tests against running server                  | unit-level mocks, browser, axe             |
| `qa-contract-test` | OpenAPI / golden-master conformance only                 | happy-path coverage (api owns that)        |
| `qa-security-test` | OWASP-aligned vulnerability tests                        | happy-path coverage; never weakens asserts |
| `qa-ui-test`       | Playwright E2E browser tests                             | API-only assertions                        |
| `qa-a11y-test`     | WCAG 2.1 AA via axe-core                                 | UI flow logic, performance                 |

Cross-category overlap is forbidden. If `qa-api-test` writes a UI assertion, the path regex rejects it (file lives under wrong category folder). Coverage math rejects it too: `coverage[ui].files` ⊆ `qa-ui-test.outputs[].path`.

---

## Status enum (closed)

| Status                | Meaning                                                            |
|-----------------------|--------------------------------------------------------------------|
| `passed`              | All `outputs[].execution_result == "passed"`                       |
| `partial`             | Some pass, some fail; agent stayed within its file budget          |
| `error`               | Agent crashed, contract violation, fatal config issue              |
| `skipped:<reason>`    | Agent did not run; `<reason>` follows the closed code list below  |

### `skipped:<reason>` codes

| Code                         | When                                                                |
|------------------------------|---------------------------------------------------------------------|
| `skipped:no_server`          | UI/api/contract/security pre-flight: server unreachable             |
| `skipped:wrong_server`       | UI: marker check failed (different process on the port)             |
| `skipped:no_url_in_server_plan` | Orchestrator passed `server_plan.url == null`                    |
| `skipped:env_removed`        | env-validator dropped this category (missing dependency)            |
| `skipped:no_signal`          | `has_signal()` returned False (e.g., backend-only project + `ui`)   |
| `skipped:not_generated`      | No output from agent (Task call returned `None` or absent)         |
| `skipped:disabled_by_caller` | Caller explicitly excluded category via `--categories=...`          |

No free-form skip reasons. Anything else → coverage-reporter normalizes to `skipped:not_generated`.

---

## Universe size = 0

If a category's universe is empty (e.g., backend-only project for `ui`), the orchestrator's `has_signal(category, analysis)` returns `False` and the category is added to `categories_skipped` with an explicit reason in Phase 2.5. The sub-agent is never dispatched. Coverage reports `pct: 0, total: 0, status: "skipped:no_signal"`.

A `pct` of `0/0` is **not** a failure — it is "nothing applicable". The HTML report renders it as "N/A" instead of a red gauge.

---

## Cross-references

- Path layout: `reference/path-contract.md`
- Language scope (TS/JS + Python only in v1): `reference/language-support.md`
- Test patterns per language/category: `reference/<category>-test-patterns.md`
