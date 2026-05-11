# domain-brief — behavior-driven test generation

## What it is

Every test-gen sub-agent may receive a `domain_brief` field in its input,
sliced from `${LOGS_DIR}/domain_brief_<category>.json` (produced by
`qa-domain-analyzer` in orchestrator Phase 2.7). It tells the sub-agent what
behaviors the source actually has, so it can stop falling back to
"401 without auth" repeated per route.

## Input shape

```json
"domain_brief": [
  {
    "expected_file": "tests/api/auth/login.api.test.ts",
    "covers": ["POST /api/login"],
    "source_files": ["apps/api/src/routes/auth.ts"],
    "behaviors": [
      {
        "trigger": "POST /api/login {email, password}",
        "expected_outcome": "200 with {token, refreshToken, user}",
        "side_effects": ["RefreshToken row created", "auditLog row created"],
        "error_paths": [
          {"trigger": "missing email",     "outcome": "400 ValidationError"},
          {"trigger": "wrong password",    "outcome": "401 InvalidCredentials"},
          {"trigger": "user.mfaEnabled",   "outcome": "200 with {mfaRequired:true}"},
          {"trigger": "5 failed attempts", "outcome": "429 RateLimited"}
        ]
      }
    ],
    "test_hints": [
      "happy_path",
      "validation_missing_field:email",
      "validation_missing_field:password",
      "auth_wrong_credentials",
      "mfa_required_branch",
      "rate_limit"
    ]
  }
]
```

The list is sliced per dispatch batch — entries cover only the
`expected_files` in this batch. When `domain_brief` is absent or empty for
an entry, the sub-agent generates a smoke-only test (one happy path) and
records `domain_brief_missing` in its warnings.

## How sub-agents must use it

For each `expected_files[i]`:

1. Locate the matching brief by `expected_file` match.
2. Generate **one `describe` / `test.describe` block per file**.
3. Generate **one `it` / `test` per entry in `brief.test_hints[]`**.
4. Each `it` must assert against the corresponding
   `brief.behaviors[*].expected_outcome` (or `error_paths[*].outcome`),
   not just an HTTP status code. For API tests, assert response body shape;
   for unit tests, assert returned value AND side effects; for UI tests,
   assert visible state on screen.
5. If a `test_hint` is `happy_path`, emit it FIRST. Negative cases follow.
6. If a `test_hint` cannot be implemented (e.g. the relevant middleware is
   not in scope of this file), record it under
   `outputs[i].skipped_hints[]` in the AgentResult — do NOT fabricate a
   passing test.

## Forbidden

- `expect(res.status).toBeGreaterThanOrEqual(400)` — too loose. Assert the
  exact status code.
- Status-only assertions when `behaviors[].expected_outcome` describes a
  payload shape — assert the shape.
- Generating fewer tests than `test_hints[]` entries without recording the
  skip reason in `skipped_hints[]`.
- Inventing hint codes. Only the closed vocabulary from `qa-domain-analyzer`
  is valid.

## Forbidden phrases in test bodies

These signal a shallow stub-equivalent and trigger the stub-marker
detection in `final_gate`:

- `expect(true).toBe(true)`
- `expect(true).toBeTruthy()`
- `assert True  # placeholder`
- Any `Auto-generated stub` comment.

## Telemetry

For each emitted file, your `outputs[i]` MUST include:

```json
{
  "path": "tests/api/auth/login.api.test.ts",
  "covers": ["POST /api/login"],
  "tests_written": 6,
  "hints_used":    ["happy_path", "validation_missing_field:email", ...],
  "skipped_hints": [],
  "vulnerabilities_found": []
}
```

`hints_used + skipped_hints` must cover every entry in the matching brief's
`test_hints[]`. This is enforced indirectly — Phase 9 stub-content gate
catches stubs; future regression check may parse `hints_used` count vs.
`it` count.

## When `domain_brief` is missing

If the input has no `domain_brief` field (e.g. older orchestrator pre-Phase
2.7), generate a minimal smoke happy-path test per `expected_files[i]` and
record `warnings: ["domain_brief_missing"]` once. Never improvise deep
domain assertions without the brief — that path used to produce wrong-shape
mocks and was the original quality gap.
