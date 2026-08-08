---
applyTo: "qa_agent/**/*.py"
---

# Engine code rules

`qa_agent/` is the deterministic half of the product: it must produce identical output for
identical input, because the LLM layer above it is only trustworthy when the phases beneath
it are reproducible.

## Do

- Keep `qa_agent/cli/commands/*` free of LLM calls and network access — those phases are
  unit-tested and must run offline.
- Guard optional dependencies (tree-sitter, ts-morph bridge) behind import-time fallbacks,
  because the `parsing` extra is optional and the engine must degrade instead of crashing.
- Use `pathlib.Path` for all filesystem work and resolve target paths from the
  `--project` argument, never from `os.getcwd()`, since the CLI runs from the plugin dir.
- Add or extend a test under `qa_agent/tests/` for every behavior change; `pytest` is the
  only gate this repo has.

## Don't

- Don't shell out to `pytest` / `npm` / `pip` outside `qa_agent/runtime/` and
  `qa_agent/executors/`, which own process handling and install planning.
- Don't let a scanner or executor raise on a malformed target project — collect the issue
  and continue, because one bad file must not abort a whole scan.
- Don't hardcode target-language assumptions; language support is dispatched through the
  tech-stack scanner.

## Verify

```bash
pytest qa_agent/tests
```

Iterate until green, then paste the summary line as evidence for the claim.
