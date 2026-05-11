# Agent Result Contract — pre-return self-validation

Every test-generation sub-agent MUST self-validate its return JSON before handing it back to the orchestrator. The cost is one Bash call; the reward is rejecting bad output at the boundary instead of letting Phase 9 catch it.

---

## How to self-validate

Pass the candidate result JSON to the shared validator:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/validate_test_output.py" --json "$RESULT_JSON"
# stdout when valid:   {"status": "pass"}
# stdout when invalid: {"status": "fail", "errors": [...]}
```

If the validator returns `fail`, the sub-agent MUST:

1. Inspect `errors[]` and try to repair the JSON deterministically (e.g., trim invalid `outputs[]` entries, replace bad `status` strings with the closed-enum equivalent).
2. Re-validate. Still failing → return:
   ```json
   {
     "agent": "<agent-name>",
     "status": "error",
     "reason": "self_validation_failed: <first error>",
     "outputs": [],
     "warnings": [/* every error from validator */]
   }
   ```

Never return invalid JSON. The orchestrator's coverage-reporter assumes contract compliance; a malformed return corrupts the report.

---

## What the validator checks

`qa_skills.validators.validate_test_output(result)` covers:

- `agent` and `status` fields present.
- `status` matches closed-enum regex `^(passed|partial|error|skipped:[a-z0-9_:]+)$`.
- `outputs` is an array.
- Every `outputs[i].path` matches the path regex `^tests/(unit|api|ui|security|a11y|contract)/(?:[^/]+/)+(test_[^/]+\.py|[^/]+\.(spec|test|api\.test|security\.test|contract\.test|a11y\.spec)\.(ts|js))$`.

Schema source: `skills/_shared/schemas/test_output.schema.json`. Acceptance tests: `skills/_shared/qa_skills/tests/test_validators.py`.

---

## Why a regex enum and not free-form strings

The legacy code shipped sub-agents that returned status strings like `skipped_no_server`, `skipped_wrong_server`, `skipped_unsupported_language`, `not_generated`. Coverage-reporter then had to enumerate every variant defensively. Every new variant required code changes in three places (sub-agent, coverage-reporter, Phase 9 gate).

The closed enum + reason suffix pattern (`skipped:<reason_code>`) lets us add new skip reasons without touching the consumer side — the validator passes any `[a-z0-9_:]+` suffix. See `reference/category-boundaries.md` for the closed reason-code list.
