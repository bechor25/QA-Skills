# Rule: state layer (`qa_agent/state/`, `qa_agent/cli/commands/`)

State under `<target-project>/.qa-agent/state/` is the contract between pipeline phases.

- Read/write state **only** through `qa_agent/state/manager.py`, because it owns atomic
  writes and Pydantic validation; direct JSON access corrupts downstream phases silently.
- Declare a model in `qa_agent/state/schemas.py` before emitting any new state file.
- Make later-phase fields optional-with-default, since the pipeline is resumable and earlier
  phases write partial documents.
- Renaming a field means updating every downstream consumer in the chain
  (`project_map → dependency_graph → knowledge_graph → risk_matrix → raw_capability_map →
  capability_map → strategy → contracts → scenarios → generated_tests → execution_history →
  critique → report-data → report.html`).
- Verify with `pytest qa_agent/tests/test_state.py`, then the full suite.

Full version: `.github/instructions/state-layer.instructions.md`.
