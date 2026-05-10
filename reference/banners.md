# Orchestrator Progress Banners

Loaded by `qa-orchestrator` to emit user-facing single-line progress banners before/after each Task invocation in Phases 1–8.

## Emoji-per-agent table

| Agent                    | Emoji |
|--------------------------|-------|
| qa-code-analyzer         | 🔍    |
| qa-git-diff-analyzer     | 📐    |
| qa-env-validator         | 🔬    |
| qa-learnings-validator   | 🧠    |
| qa-unit-test             | 🧪    |
| qa-api-test              | 🌐    |
| qa-ui-test               | 🖥️    |
| qa-security-test         | 🔒    |
| qa-a11y-test             | ♿    |
| qa-contract-test         | 📋    |
| qa-flaky-detector        | 🎲    |
| qa-coverage-reporter     | 📊    |
| qa-html-reporter         | 📄    |

## Format

```
Before (en):  {emoji} {agent} | {short_action}...
Before (he):  {emoji} {agent} | {short_action_he}...
After  (en):  {emoji} {agent} | {short_outcome} ({elapsed}s)
After  (he):  {emoji} {agent} | {short_outcome_he} ({elapsed} שניות)
Skipped:      {emoji} {agent} | ⏭️ skipped: {reason}

Parallel batch:
⚡ DISPATCH PARALLEL
  {emoji} {agent_1} | {short_action}...
  {emoji} {agent_2} | {short_action}...
```
After parallel batch returns, emit each agent's "after" line in completion order.

## Examples

```
🔍 qa-code-analyzer | scanning code... done (12s, 28 modules, 14 routes)
📐 qa-git-diff-analyzer | classifying diffs... done (2s, 6 changed)
🔬 qa-env-validator | checking deps... installed pytest-playwright (3s)
🧠 qa-learnings-validator | loading priors... 8 confirmed, 3 candidates (1s)

⚡ DISPATCH PARALLEL
  🧪 qa-unit-test | generating unit tests...
  🌐 qa-api-test | generating api tests...
  🔒 qa-security-test | generating security tests...

🧪 qa-unit-test | 12 tests passed (45s, sonnet)
🌐 qa-api-test | 8 tests passed (38s, sonnet)
🔒 qa-security-test | 4 tests passed (52s, opus)

🎲 qa-flaky-detector | 3 reruns... 0 flaky (90s)
📊 qa-coverage-reporter | aggregating... report saved (8s)
📄 qa-html-reporter | rendering... opened in browser (3s)
```

## Rules

- One banner BEFORE each Task call. One AFTER each Task call.
- Banner is plain text in orchestrator response, NEVER inside a tool call argument.
- Never emit banners INSIDE the JSON return value to caller — only as conversational text.
- Sub-agents themselves do NOT emit banners — Task tool captures their text. Only orchestrator emits.
- Skip banner only if Task call is a no-op decided pre-emptively (env-validator removed category before dispatch → one `⏭️ skipped` line).
- Locale: derive `short_action` / `short_outcome` from caller's `locale`.
  - Action verbs (he): `סורק`, `מתקין`, `יוצר`, `מריץ`, `מסיים`.
  - Outcomes (he): `הסתיים`, `דולג`, `נכשל`.
