# Language Support

QA-Skills v1 supports **TypeScript / JavaScript** and **Python** end-to-end. Other languages (Java, Kotlin, C#, Go, Ruby) are NOT supported in v1 and will return `status: error, reason: "unsupported_language"` from `qa-code-analyzer`.

---

## Detection (qa-code-analyzer Phase 1)

| Signal                                      | Language → `analysis.language` |
|---------------------------------------------|--------------------------------|
| `package.json` exists                       | `typescript` (or `javascript` if no `tsconfig.json`) |
| `requirements.txt` / `pyproject.toml` exists| `python`                       |
| Both exist                                  | `multi` — primary detected from majority of source files |
| Neither                                     | `error: unsupported_language`  |

`run_context.schema.json` enum: `typescript | javascript | python | multi`.

---

## Test framework matrix

| Category | TypeScript / JavaScript          | Python                       |
|----------|----------------------------------|------------------------------|
| unit     | Vitest (preferred) or Jest       | pytest + unittest.mock       |
| api      | supertest + (Vitest / Jest)      | httpx + pytest               |
| contract | ajv + ajv-formats                | jsonschema                   |
| security | supertest + (Vitest / Jest)      | httpx + pytest               |
| ui       | `@playwright/test`               | pytest-playwright            |
| a11y     | `@playwright/test` + `@axe-core/playwright` | pytest-playwright + axe-playwright-python |

Vitest is preferred over Jest when `vitest.config.*` is detected. env-validator installs missing dependencies via `npm install -D` / `pip install`.

---

## Path regex per language

Both languages share a single category-aware regex (see `reference/path-contract.md`):

```
^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+(test_[^/]+\.py|[^/]+\.(spec|test|api\.test|security\.test|contract\.test|a11y\.spec)\.(ts|js))$
```

| Language          | File pattern                              |
|-------------------|-------------------------------------------|
| Python            | `test_<name>.py`                          |
| TypeScript / JS   | `<name>.{spec,test,api.test,security.test,contract.test,a11y.spec}.{ts,js}` |

The orchestrator's `qa_skills.path_planner` produces filenames matching the pattern automatically — sub-agents do not pick filenames.

---

## Test runners

| Language | Run command (per test file)                                                                              |
|----------|----------------------------------------------------------------------------------------------------------|
| Python   | `pytest <test_path> --tb=short -q --json-report --json-report-file=.qa-skills/pytest-results.json`       |
| TS/JS    | `npx jest <test_path> --json --outputFile=.qa-skills/jest-results.json` (Jest) or `npx vitest run <test_path> --reporter=json` (Vitest) |

Whole-suite re-runs (qa-flaky-detector): drop the `<test_path>` argument.

---

## Adding a new language (out-of-scope for v1)

To add Java/C#/Go/Ruby in v2:

1. Update `analysis.schema.json` `language` enum.
2. Update `qa-code-analyzer.md` Phase 1 detection table + Phase 2 regex blocks.
3. Update `qa_skills.path_planner._testname()` for the new file extension.
4. Update `qa_skills.validators.PATH_REGEX` with the new file pattern.
5. Add framework rows to `qa-env-validator.md` + framework tables in test-gen agents.
6. Add code samples to `reference/<category>-test-patterns.md`.
7. Add fixtures + planner tests under `skills/_shared/qa_skills/tests/fixtures/`.

If any of those is missed → the run will silently skip files for that language. Acceptance pytest catches gaps.
