# Changelog

## [Unreleased] — v2.0.0 build-in-progress

Full rewrite from v1. Track progress in `ROADMAP.md`.

### Phase 0 — Foundation (in progress)
- Plugin manifest bumped to 2.0.0.
- New Python package `qa_agent` with CLI (`qa-agent`).
- State layer: pydantic schemas + atomic JSON `StateManager`.
- Shared utilities: logging, paths, jsonio, git, config, errors.
- CLI subcommands stubbed: `full-run`, `analyze`, `rerun`, `report`, `state`.
- Defaults config at `configs/defaults.yaml`.
