---
description: Scaffold a new qa-agent pipeline phase (CLI or AGENT) with its state model, wiring, and tests.
---

Add a new pipeline phase named `$ARGUMENTS` to the `qa-agent` engine. Follow this order,
because state is the contract between phases and every later step depends on the model
existing first.

1. **Decide the owner.** Deterministic work → a CLI phase under
   `qa_agent/cli/commands/`. Bounded LLM authoring → an `agents/<name>.md` sub-agent
   dispatched by `skills/test-orchestrator`. Never mix the two in one phase.
2. **Model the output.** Add a Pydantic model to `qa_agent/state/schemas.py` and an
   accessor to `qa_agent/state/manager.py`. Later-phase fields are optional-with-default so
   a resumed run can load partial state.
3. **Implement.**
   - CLI: new module in `qa_agent/cli/commands/`, registered in the CLI entry point, taking
     `--project PATH`. No network, no LLM.
   - AGENT: new `agents/<name>.md` naming exactly one output artifact and its schema.
4. **Wire the orchestrator.** Add the phase to the pipeline table in
   `skills/test-orchestrator/references/pipeline.md` and, if it changes resume behavior, to
   the resume matrix in `references/resume.md`.
5. **Document.** Update the chain diagram in `CLAUDE.md`, `AGENTS.md`, and
   `ARCHITECTURE.md` so the contract stays discoverable.
6. **Test.** Add a round-trip test in `qa_agent/tests/test_state.py` plus a behavior test
   for the phase itself, then run `pytest qa_agent/tests` and iterate until green.
7. Report the pytest summary output as evidence.
