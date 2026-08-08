---
mode: agent
description: Add a new qa-agent pipeline phase end to end — state model, implementation, orchestrator wiring, docs, tests.
---

Add a new pipeline phase to the `qa-agent` engine. Follow this order, because state is the
contract between phases and everything downstream depends on the model existing first.

1. **Choose the owner.** Deterministic work → a CLI phase in `qa_agent/cli/commands/`.
   Bounded LLM authoring → an `agents/<name>.md` sub-agent fanned out by
   `skills/test-orchestrator`. Never mix both in one phase, since CLI phases must stay
   reproducible without a model.
2. **Model the output** in `qa_agent/state/schemas.py` and add an accessor in
   `qa_agent/state/manager.py`. Later-phase fields are optional-with-default so a resumed
   run can load partial state.
3. **Implement** the phase. CLI phases take `--project PATH`, do no network I/O, and never
   call an LLM.
4. **Wire it** into `skills/test-orchestrator/references/pipeline.md`, and into
   `references/resume.md` if it changes resume behavior.
5. **Document** the new link in the dependency chain in `CLAUDE.md`, `AGENTS.md`, and
   `ARCHITECTURE.md`.
6. **Test**: round-trip test in `qa_agent/tests/test_state.py` plus a behavior test; run
   `pytest qa_agent/tests` and iterate until green, then paste the summary as evidence.
