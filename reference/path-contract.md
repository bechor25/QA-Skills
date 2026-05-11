# Path Contract — `expected_files` & `covers[]` semantics

This document is the single source of truth for how the orchestrator hands work to test-generation sub-agents. Every sub-agent reads only its own row in the table below; do not improvise.

---

## Authority

The orchestrator's Phase 2.5 computes the deterministic plan via `compute_expected_files(category, analysis, language)` (see `qa-orchestrator.md`). The plan is written to `${logs_dir}/expected_files.json` and a slice is passed to each sub-agent inside its `path_contract.expected_files`.

**Sub-agent rule:** read `path_contract.expected_files`, write **exactly** those paths, fill them with appropriate test code. Nothing more, nothing less.

If `expected_files` is missing or empty → return `{"status": "error", "reason": "missing_path_contract"}`. Do **not** improvise paths.

---

## `expected_files` shape

Always a JSON array of `{path, covers}` objects:

```json
[
  {"path": "tests/api/auth/test_login.py", "covers": ["POST /api/login"]},
  {"path": "tests/api/users/test_users.py", "covers": ["GET /api/users", "GET /api/users/{id}"]}
]
```

- `path` — project-relative test file path. Validated against `path_contract.required_pattern`.
- `covers` — non-empty array of items the file must cover (semantics depend on category — see table below).

**Forbidden:** `null`, empty array, missing keys, paths outside `tests/<category>/`.

---

## `covers[]` semantics by category

The format of every entry in `covers[]` depends on the category. Sub-agents must produce assertions that exercise these exact items.

| Category   | `covers[]` element format                | Source field                                        | Example                          |
|------------|------------------------------------------|-----------------------------------------------------|----------------------------------|
| `unit`     | source module path                       | `analysis.modules[].path`                           | `"app/auth.py"`                  |
| `api`      | `"METHOD /path"` (one space, exact case) | `analysis.routes[]` where `kind == "api"`           | `"POST /api/login"`              |
| `contract` | `"METHOD /path"`                         | `analysis.routes[]` where `kind == "api"`           | `"GET /api/users/{id}"`          |
| `security` | `"METHOD /path"`                         | `analysis.routes[]` where `kind == "api"`           | `"POST /api/register"`           |
| `ui`       | frontend file path                       | `analysis.frontend_files[].path` where `kind=page`  | `"templates/login.html"`         |
| `a11y`     | frontend file path                       | `analysis.frontend_files[].path` where `kind=page`  | `"templates/login.html"`         |

**Hard rule:** `covers[]` entries are **never null** and **never empty strings**. The orchestrator validates this before dispatch; sub-agents validate again before treating any entry.

---

## Sub-agent consumption pattern

```python
expected = path_contract.get("expected_files") or []
policy   = path_contract.get("policy", "exact")

if not expected:
    return {"status": "error", "reason": "missing_path_contract"}

if policy != "exact":
    return {"status": "error", "reason": f"unsupported_policy:{policy}"}

for entry in expected:
    path   = entry["path"]
    covers = entry["covers"]
    if not covers:
        return {"status": "error", "reason": f"empty_covers_for_path:{path}"}

    # Resolve targets from the analysis slice the orchestrator passed in.
    if category == "unit":
        # m["path"] is the canonical source-path field — see analysis.schema.json.
        targets = [m for m in modules if m.get("path") in covers]
    elif category in ("api", "contract", "security"):
        # Match by "METHOD /path" string identity.
        targets = [r for r in routes if f"{r['method']} {r['path']}" in covers]
    elif category in ("ui", "a11y"):
        targets = [f for f in frontend_files if f.get("path") in covers]
    else:
        return {"status": "error", "reason": f"unknown_category:{category}"}

    write_test_file(path, targets)

return {"status": "passed", "outputs": [...]}
```

---

## What sub-agents DO NOT do

- **Do not call `derive_domain_and_tag`.** That function lives in the orchestrator only. Sub-agents that re-derive paths drift from the contract.
- **Do not consult `analysis.modules` / `analysis.routes` / `analysis.frontend_files` to choose paths.** Use them only to fill content for the paths the orchestrator already chose.
- **Do not consolidate two `expected_files` entries into one mega file** — even if their `covers[]` overlap.
- **Do not split one `expected_files` entry into multiple files** — even if a single file looks too large.
- **Do not read `m["file"]` or `m["name"]`.** The schema defines `m["path"]`. Reading non-existent keys silently returns `""` and produces empty `covers[]`.

---

## Error codes (sub-agent → orchestrator)

| code                              | meaning                                                |
|-----------------------------------|--------------------------------------------------------|
| `missing_path_contract`           | `expected_files` empty or missing                      |
| `unsupported_policy:<x>`          | `policy` other than `"exact"`                          |
| `empty_covers_for_path:<path>`    | `covers[]` empty for an entry                          |
| `path_regex_violation:<path>`     | path failed `required_pattern` regex                   |
| `target_not_found:<cover>`        | item in `covers[]` not present in analysis slice       |
| `unsupported_language:<lang>`     | language not in v1 (TS/JS/Python)                      |

The orchestrator translates these into `categories_skipped` reasons or run-level warnings.

---

## Why this contract exists

Before this contract, sub-agents independently re-derived paths via `derive_domain_and_tag()` and a per-agent fallback flow. Outputs drifted from the orchestrator's plan. Phase 9 had to detect and clean up extras post-hoc — wasting the work that produced them.

After this contract:
- Path planning happens once, in `compute_expected_files()`.
- Sub-agents fill in code; they never decide structure.
- Phase 9 verifies disk matches plan; it never deletes work the system shouldn't have produced.
