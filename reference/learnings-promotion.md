# Learnings — Promotion, Demotion, Decay

This file is the contract for tier transitions in `learnings.json`. Validator and coverage-reporter MUST follow these rules.

## States

```
new finding
   |
   v
candidate ──(occurrences>=3)──>  confirmed
   |                                   |
   |  (occurrences=1 AND age>5 runs)   |  (module_hash changed)
   v                                   v
aged_out (drop)                    candidate (demote, occurrences=0)

dismissed_intentional ──(forever)──> not in priors, not promoted
```

## Promotion: candidate → confirmed

Coverage-reporter (Phase 5.5) runs this check on every existing entry after merging the current run:

```python
PROMOTION_THRESHOLD = 3

def maybe_promote(entry, run_id):
    if entry["tier"] != "candidate":
        return
    if run_id not in entry["evidence_runs"]:
        return  # current run did not re-confirm
    if entry["occurrences"] >= PROMOTION_THRESHOLD:
        entry["tier"] = "confirmed"
        log("promote", id=entry["id"], from_tier="candidate", to_tier="confirmed",
            trigger=f"{PROMOTION_THRESHOLD}_occurrences")
```

Threshold is `3`. Single-run flukes never reach `confirmed`. To change, bump schema version.

## Demotion: confirmed → candidate

Triggered by validator (Phase 0.5) when ground truth changes.

```python
def maybe_demote(entry, project_root):
    mp = Path(project_root) / entry["module_path"]
    if not mp.is_file():
        return drop(entry, reason="module_path_gone")
    new_hash = sha256(mp.read_bytes()).hexdigest()
    if new_hash == entry["module_hash"]:
        return  # unchanged
    # code changed: prior cannot be trusted
    log("demote", id=entry["id"], from_tier=entry["tier"], to_tier="candidate",
        trigger="module_hash_changed", old_hash=entry["module_hash"][:8], new_hash=new_hash[:8])
    entry["tier"]         = "candidate"
    entry["occurrences"]  = 0
    entry["module_hash"]  = new_hash
    entry["evidence_runs"] = []
```

Why occurrences reset: refactor may have fixed the bug. Re-prove from scratch.

`line_range` is NOT updated automatically — it stays as last-known. Sub-agent in next run rediscovers actual line.

## Decay: aged_out

Validator drops entries that have not been re-confirmed.

```python
DECAY_RULES = [
    # candidate that never repeated
    {"tier": "candidate", "occurrences": 1, "max_age_runs": 5,  "reason": "stale_candidate"},
    # any entry untouched for too long
    {"any_tier": True,    "max_age_days": 90,                   "reason": "aged_out"},
]
```

`dismissed_intentional` entries are NEVER aged out. User truth is permanent.

## Dismissal: user-driven

Triggered by `/qa-skills:learnings dismiss <id> --reason <text>` slash command (or interactive prompt at end of run).

```python
def dismiss(entry, reason):
    entry["user_status"]    = "dismissed_intentional"
    entry["dismiss_reason"] = reason
    log("dismiss", id=entry["id"], actor="user", reason=reason)
```

Dismissed entries:
- Excluded from `priors` passed to sub-agents (validator filters them out).
- Never re-suggested.
- Counted in `category_effectiveness.kept` as a deduction (signals `user_kept = generated - dismissed`).
- Survive demotion — even if `module_hash` changes, dismissal stands. Treated as "user accepted the trade-off intentionally; do not re-raise even after refactors."

## Acceptance: user-driven

```
/qa-skills:learnings accept <id>
```

`user_status: "accepted"` — user wants to keep this finding visible (it's a real bug, scheduled for fix). Same downstream behavior as `open`, but dashboard renders differently.

## Confidence weight (advisory)

Coverage-reporter computes a per-entry weight used by orchestrator's strategy phase to prioritize next run. Not stored — computed on read.

```python
def confidence_weight(entry):
    base = {"candidate": 0.4, "confirmed": 0.9}[entry["tier"]]
    # source weight (set when finding was first written)
    source_w = entry.get("source_weight", 0.5)
    # recency boost: seen in last run = full weight, else decay linearly over 30 days
    age = days_since(entry["last_seen"])
    recency = max(0.3, 1.0 - age / 30.0)
    return base * source_w * recency
```

`source_weight` per agent (set at write time):

| source agent      | weight | rationale                           |
|-------------------|--------|-------------------------------------|
| qa-flaky-detector | 1.0    | empirical, 3-run reproduction       |
| qa-security-test  | 0.9    | test failed; high signal            |
| qa-api-test       | 0.9    | test failed; high signal            |
| qa-unit-test      | 0.9    | test failed; high signal            |
| qa-contract-test  | 0.85   | OpenAPI drift; high signal          |
| qa-a11y-test      | 0.8    | axe-core finding; reproducible      |
| qa-code-analyzer  | 0.4    | regex heuristic; low signal         |
| LLM commentary    | 0.0    | **never written** — no entry created |

Heuristic-only findings (`source_weight ≤ 0.4`) cannot reach `confirmed` even at 3 occurrences unless the agent supplies a failing test in `test_path`. Without a test, the entry is rejected by `can_write_finding` regardless of recurrence.

## Audit log invariants

Every state transition appends a single JSONL line to `learnings.log`. The log is append-only — never rewritten in place.

```jsonl
{"ts":"...","action":"add","tier":"candidate","id":"...","reason":"qa-security-test:run_1","evidence":"tests/security/auth/auth.security.test.py::test_x"}
{"ts":"...","action":"increment","id":"...","occurrences":2,"run":"run_2"}
{"ts":"...","action":"promote","id":"...","from":"candidate","to":"confirmed","trigger":"3_occurrences"}
{"ts":"...","action":"demote","id":"...","from":"confirmed","to":"candidate","trigger":"module_hash_changed"}
{"ts":"...","action":"drop","id":"...","reason":"aged_out","at_age_days":91}
{"ts":"...","action":"dismiss","id":"...","actor":"user","reason":"intentional dev backdoor"}
{"ts":"...","action":"reject","reason":"unknown_rule","value":"imaginary_xyz","run":"run_5"}
```

`tail learnings.log` is the canonical debug surface. Manual revert: read log, identify offending action, edit `learnings.json` directly. The log itself is not edited.
