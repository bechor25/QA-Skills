# Install — qa-skills plugin

## Requirements

- Claude Code CLI v2+ (`claude --version`)
- Python 3.11+ available on `PATH` (the plugin auto-creates an isolated
  venv; nothing is installed into the user's global Python)
- Node.js + npm (only required if you intend to run the generated
  TypeScript tests; not needed for plugin install itself)

## Install

```bash
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```

The plugin is now available in every Claude Code session. No further
setup is required — the Python venv is created on the first invocation.

## First run

```bash
cd ~/path/to/your/project
claude
```

Inside the session, just say:

```
run qa
```

(Hebrew triggers also work: `הרץ qa`, `צור בדיקות`.)

What happens behind the scenes:

1. The `test-orchestrator` skill matches the trigger phrase.
2. It hands off to the `qa-master` agent.
3. The agent calls `${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run full-run --project "${PROJECT_ROOT}"`.
4. On the very first call (per machine), the wrapper bootstraps a Python
   venv under `${CLAUDE_PLUGIN_ROOT}/.venv` and `pip install`s the
   `qa-agent` package. Takes ~20–40 s.
5. Subsequent calls reuse the venv and start instantly.
6. The pipeline scans → KG → risk → strategy → scenarios → generates →
   installs test deps → executes → heals → reports.
7. The agent prints the quality score, the HTML report path, and the
   top 3 risks.

## Verifying install

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/qa-skills-run" --help
```

You should see the `qa-agent` CLI usage. If you get
`qa-skills: Python 3.11+ is required`, install Python 3.11+ and retry.

## Updating

```bash
claude plugin update qa-skills
```

After an update, the venv stays — only the source code is refreshed. The
editable install (`pip install -e`) means the venv picks up new code
automatically; no rebuild needed unless dependencies in `pyproject.toml`
changed. If you suspect a stale venv:

```bash
rm -rf "${CLAUDE_PLUGIN_ROOT}/.venv"
```

The next run will rebuild it.

## Uninstall

```bash
claude plugin uninstall qa-skills
claude plugin marketplace remove bechor25/QA-Skills
```

This removes the plugin and its venv. Generated test artifacts in your
project's `.qa-agent/` directory are left untouched — delete that
directory manually if you want to clean up.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude: command not found` | Install Claude Code CLI first. |
| `qa-skills: Python 3.11+ is required` | Install Python 3.11+; the plugin won't downgrade. |
| `pip install` step hangs on first run | Check network connectivity. `pip` install runs against PyPI. |
| `qa-agent` not found after a successful first run | Delete `${CLAUDE_PLUGIN_ROOT}/.venv` and retry — the venv exists but the binary symlink is broken. |
| Report path printed but no browser opens | Run `claude` and say `open qa report` — the `view-report` skill will reopen the latest. |
