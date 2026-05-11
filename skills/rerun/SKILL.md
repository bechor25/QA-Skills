---
name: rerun
description: Re-execute a previously generated test suite. Triggers on "rerun", "rerun tests", "rerun failed", "rerun flaky", "rerun changed", "הרץ שוב", "הרץ נכשלים", "הרץ flaky".
---

# rerun

The user wants to re-execute a subset of the previously generated tests.

## Pick a scope

| User phrase                        | Scope     |
|------------------------------------|-----------|
| "failed", "the failures", "נכשלים" | `failed`  |
| "flaky", "unstable", "לא יציבים"  | `flaky`   |
| "changed", "what I modified", "שינויים" | `changed` |
| "all", "everything", "הכל"        | `all`     |

If unclear, default to `changed`.

## Hand off

> Run `qa-agent rerun --scope <chosen> --project "${PWD}"`. Then read the
> last log line for the failed count and surface the per-category breakdown
> from `state/execution_history.json` (last `run_id` only).

## Constraints

- Do not regenerate tests. Re-running uses what's already in
  `state/generated_tests.json`.
- Do not run the full pipeline. If `state/generated_tests.json` is empty,
  tell the user they need to call **test-orchestrator** first.
