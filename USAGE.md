# Usage

## Quick start

In any project directory, open Claude Code and say:

```
run qa
```

Claude triggers `qa-agent full-run` and reports back with the HTML report path.

## CLI reference

### `qa-agent full-run`
End-to-end pipeline: scan → strategy → generate → execute → report.

```bash
qa-agent full-run                    # current directory
qa-agent full-run --project /path    # explicit
qa-agent full-run --categories ui,api,security
qa-agent full-run --no-llm           # skip LLM-driven phases (debug only)
```

### `qa-agent analyze`
Scan + knowledge-graph + risk-matrix only. No tests generated.

```bash
qa-agent analyze --project /path
```

Outputs:
- `<project>/.qa-agent/state/project_map.json`
- `<project>/.qa-agent/state/dependency_graph.json`
- `<project>/.qa-agent/state/knowledge_graph.json`

### `qa-agent rerun`
Re-execute a previously generated suite. Scope controls what runs:

| Scope     | Re-runs                                                  |
|-----------|----------------------------------------------------------|
| `changed` | Tests for modules changed since last run (git diff).     |
| `failed`  | Only tests that failed in the last run.                  |
| `flaky`   | Tests marked unstable in `flaky_state.json`.             |
| `all`     | Everything.                                              |

```bash
qa-agent rerun --scope changed
```

### `qa-agent report`
Render and optionally open the HTML report.

```bash
qa-agent report --open
```

### `qa-agent state`
Inspect or wipe project state.

```bash
qa-agent state show
qa-agent state reset
```

## State files

Everything is under `<project>/.qa-agent/state/`. See `ROADMAP.md` §4 for the
complete table.

## Configuration

Drop `<project>/.qa-agent/config.yaml` to override defaults from
`<plugin>/configs/defaults.yaml`. Override keys are shallow-merged.
