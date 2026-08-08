# Rule: engine code (`qa_agent/**/*.py`)

- `qa_agent/cli/commands/*` stays LLM-free and offline, because these phases are unit-tested
  and must be reproducible without a model.
- Optional deps (tree-sitter, ts-morph bridge) sit behind import fallbacks so a missing
  `parsing` extra degrades instead of crashing.
- Use `pathlib.Path` and resolve target paths from `--project`, never `os.getcwd()`, since
  the CLI process runs from the plugin directory.
- Process spawning and install planning live in `qa_agent/runtime/` and `qa_agent/executors/`
  only.
- Scanners never raise on a malformed target file — collect and continue, because one bad
  file must not abort a scan.
- Every behavior change gets a test under `qa_agent/tests/`; run `pytest qa_agent/tests` and
  iterate until green, then show the output.

Full version: `.github/instructions/engine.instructions.md`.
