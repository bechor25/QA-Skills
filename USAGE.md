# Usage

## Quick start

In any project directory, open Claude Code and say:

```text
run qa
```

The `test-orchestrator` skill triggers the full QA flow and returns the path to
the generated HTML report.

After a run, if pass-rate is low, say:

```text
heal tests
```

(`תקן בדיקות` in Hebrew). The `test-fixer` skill operates on the existing run:
it root-cause-clusters the failures, applies the few shared
harness/config/seed fixes once, fans out per-test fixers for the residue, and
loops with rollback safety until quality plateaus. It refuses if there is no
prior run, never edits application source, and reports product bugs instead of
patching them (so the score stays honest).

## CLI reference

### `qa-agent analyze`

Scan the project and build the knowledge graph and risk matrix.

```bash
qa-agent analyze --project /path
```

Outputs:

- `<project>/.qa-agent/state/project_map.json`
- `<project>/.qa-agent/state/dependency_graph.json`
- `<project>/.qa-agent/state/knowledge_graph.json`
- `<project>/.qa-agent/state/risk_matrix.json`

### `qa-agent prepare`

Run `analyze`, then discover raw capabilities, UI selectors, and test-data hints.

```bash
qa-agent prepare --project /path
```

Outputs:

- `<project>/.qa-agent/state/raw_capability_map.json`
- `<project>/.qa-agent/state/ui_selectors.json`
- `<project>/.qa-agent/state/test_data_plan.json`

### `qa-agent build-strategy`

Rebuild `strategy.json` from the refined capability map.

```bash
qa-agent build-strategy --project /path
```

### `qa-agent scaffold`

Group scenarios by `(capability, category)` and emit scaffolded test files.

```bash
qa-agent scaffold --project /path
```

### `qa-agent run-tests`

Execute generated suites. Use `--skip-install` when the environment is already prepared.

```bash
qa-agent run-tests --project /path
qa-agent run-tests --project /path --skip-install
qa-agent run-tests --project /path --timeout 300
```

### `qa-agent retry-decide`

Read execution history and triage verdicts, then print retry decisions as JSON.

```bash
qa-agent retry-decide --project /path
```

### `qa-agent rerun`

Re-execute a scoped subset of generated tests.

| Scope | Re-runs |
|---|---|
| `changed` | Tests for modules changed since the last run |
| `failed` | Tests that failed in the latest run |
| `flaky` | Tests classified as flaky |
| `all` | Every generated test |

```bash
qa-agent rerun --project /path --scope changed
```

### `qa-agent heal-diagnose` / `heal-apply` / `heal-rerun` / `heal-status`

The deterministic half of the `test-fixer` skill (the heal loop). The skill
drives these; you rarely call them by hand.

```bash
qa-agent heal-diagnose --project /path            # cluster failures (systemic vs per_test)
qa-agent heal-diagnose --project /path --no-run   # reparse last run's logs instead of executing
qa-agent heal-apply --project /path --target tests/qa-agent/global-setup.ts --kind harness --iteration 1 --patch -
qa-agent heal-apply --project /path --kind dep --dep "npm -D @playwright/test"
qa-agent heal-apply --project /path --revert 1    # roll back iteration 1
qa-agent heal-rerun --project /path --scope all --iteration 1 --tier systemic
qa-agent heal-status --project /path              # loop decision JSON (read-only)
```

| File | Owner |
|---|---|
| `heal_failures.json` | `heal-diagnose` (structured per-test failures) |
| `heal_clusters.json` | `heal-diagnose` (root-cause groups) |
| `heal_journal.json` | `heal-apply` (rollback snapshots) |
| `heal_ledger.json` | `heal-rerun` (per-iteration pass deltas) |

### `qa-agent report`

Render and optionally open the HTML report.

```bash
qa-agent report --project /path --open
```

### `qa-agent state`

Inspect or reset project state.

```bash
qa-agent state --project /path show
qa-agent state --project /path reset
```

### `qa-agent full-run`

Compatibility path for a direct end-to-end run through the Python engine.

```bash
qa-agent full-run --project /path
qa-agent full-run --project /path --categories ui,api,security
qa-agent full-run --project /path --no-llm
```

## State files

Everything lives under `<project>/.qa-agent/state/`. See `ROADMAP.md` for the
full file map and ownership table.

## Configuration

Drop `<project>/.qa-agent/config.yaml` to override defaults from
`<plugin>/configs/defaults.yaml`. Override keys are shallow-merged.
