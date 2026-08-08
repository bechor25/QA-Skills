---
applyTo: "qa_agent/state/**,qa_agent/cli/commands/**,qa_agent/report/**"
---

# State layer rules

State under `<target-project>/.qa-agent/state/` is the contract between every pipeline
phase. `qa_agent/state/manager.py` is the **only** supported read/write path, because it
owns atomic writes, path resolution, and Pydantic validation — any module that opens those
JSON files directly bypasses validation and silently corrupts a later phase.

## Do

- Add a typed model in `qa_agent/state/schemas.py` before writing any new state file, so the
  file has a schema the whole chain can rely on.
- Read and write through `StateManager` helpers only.
- Keep every field optional-with-default when it is produced by a later phase, because the
  pipeline is resumable and earlier phases must be able to write a partial document.
- Cover new state models with a test in `qa_agent/tests/test_state.py` — the round-trip test
  is what catches schema drift before a user's run does.

## Don't

- Don't `json.load` / `json.dump` a state file from a scanner, generator, executor, or
  report module.
- Don't rename or reshape an existing field without updating every downstream consumer in
  the chain below, since each phase's input is the previous phase's output.
- Don't write state from an LLM agent prompt without a matching schema entry.

## The dependency chain

```
project_map → dependency_graph → knowledge_graph → risk_matrix
  → raw_capability_map → capability_map → strategy
  → contracts/<cap> → scenarios/<cap> → generated_tests
  → execution_history → critique/<test_id> → report-data → report.html
```

## Verify

Run `pytest qa_agent/tests/test_state.py` first for a fast signal, then the full
`pytest qa_agent/tests` before claiming the change is done, and paste the summary line as
evidence.
