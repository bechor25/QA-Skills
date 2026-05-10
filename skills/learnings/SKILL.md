---
name: learnings
description: >
  Inspect and curate the QA-Skills learnings memory for a project. View confirmed/candidate
  findings, dismiss false positives, accept findings as known issues, or wipe the memory.

  English triggers: "show learnings", "qa learnings", "view findings", "dismiss finding",
  "accept finding", "clear learnings", "what has qa-skills learned".

  Hebrew triggers (טריגרים בעברית): "הצג למידה", "מה למדנו", "מה הסקיל למד",
  "דחה ממצא", "אשר ממצא", "נקה למידה", "אפס למידה".

  Operates on `${project_root}/.qa-skills/learnings.json`. Read-mostly. Writes are explicit user actions.
---

# learnings (inspector + curator)

Thin slash command. Reads the per-project learnings memory and applies user-driven state changes.

## Subcommands

```
/qa-skills:learnings                  → view (default)
/qa-skills:learnings view             → list confirmed + candidates
/qa-skills:learnings view --all       → include dismissed + flaky
/qa-skills:learnings view <id>        → detail one entry
/qa-skills:learnings dismiss <id> --reason "<text>"
/qa-skills:learnings accept <id>
/qa-skills:learnings clear            → wipe (interactive confirm only)
/qa-skills:learnings stats            → counts by category, promotion rates
```

## Behavior

1. Detect locale (Hebrew chars → `he`, else `en`).
2. Resolve `project_root` (cwd by default; honor `--project=<path>`).
3. **Emit entry banner**:
   - en: `🧠 qa-skills:learnings | {subcommand} on {project_root}...`
   - he: `🧠 qa-skills:learnings | {subcommand} על {project_root}...`
4. Verify `${project_root}/.qa-skills/learnings.json` exists. Else print:
   - en: `No learnings yet. Run /qa-skills:test-orchestrator first.`
   - he: `אין למידה עדיין. הרץ /qa-skills:test-orchestrator קודם.`
5. Parse JSON. Reject if `version != "1.0"`.
6. Dispatch to subcommand handler.
7. **Emit exit banner** after the subcommand finishes (skip for `view` since output IS the result):
   - en: `🧠 qa-skills:learnings | {subcommand} done`
   - he: `🧠 qa-skills:learnings | {subcommand} הסתיים`

All actions append a JSONL line to `${project_root}/.qa-skills/learnings.log`.

## view (default)

Render a compact table per category. Group `vuln_patterns[]` by category. Show:

```
[security]
  ✅ confirmed (3)
    • <id-short> jwt_alg_none_accepted        app/auth.py:45-58       3× last 2026-05-09
    • <id-short> sql_injection_param          app/users.py:120-145    5× last 2026-05-08
    • <id-short> idor_unauthorized_access     app/posts.py:30-55      3× last 2026-05-07
  🟡 candidates (2)
    • <id-short> none_input_guard_missing     app/auth.py:34-38       1× last 2026-05-10
    • <id-short> mass_assignment              app/users.py:60-72      2× last 2026-05-09

[unit] ...

flaky tests (2):
  • <id-short> tests/test_login.py::test_redirect      flake_count=4   last 2026-05-08
```

`--all` also lists `dismissed_intentional` entries with their `dismiss_reason`.

`view <id>`: render the full entry JSON plus the last 5 audit log lines for that id.

## dismiss

```
/qa-skills:learnings dismiss <id> --reason "intentional dev backdoor"
```

Behavior:
1. Find entry by `id` (prefix match OK if unique).
2. Confirm via `AskUserQuestion`:
   - en: `Dismiss '<rule>' on <module_path>? This is permanent — survives demotion and decay.`
   - he: `לדחות את '<rule>' על <module_path>? זה לצמיתות — שורד דמותציה וגירעון.`
3. On confirm:
   - `entry.user_status = "dismissed_intentional"`
   - `entry.dismiss_reason = <reason>`
   - Atomic write `learnings.json`.
   - Append log: `{"ts":"...","action":"dismiss","id":"...","actor":"user","reason":"<text>"}`.

`--reason` is required; reject if missing or under 5 chars.

## accept

```
/qa-skills:learnings accept <id>
```

Marks `user_status = "accepted"`. Same write/log pattern. No reason required. Dashboard renders these distinct from `open`. Future runs still re-confirm them; promotion logic unchanged.

## clear

```
/qa-skills:learnings clear
```

Interactive only — never proceeds without explicit confirm. Two-step:
1. Show summary: `N entries (X confirmed, Y candidates, Z dismissed). This will erase all of them.`
2. AskUserQuestion: `Type 'wipe' to confirm.`
3. On confirm: rename `learnings.json` to `learnings.json.bak.<timestamp>`. Log a single `{"action":"wipe","actor":"user"}` line. Do NOT delete the log itself.

Never offer `clear` non-interactively. No `--yes` flag.

## stats

Compute and print:

```
Total: 28 entries
  vuln_patterns: 21 (confirmed=8, candidate=11, dismissed=2)
  flaky_history:  7

By category:
  security  12 (4 confirmed)
  unit       6 (2 confirmed)
  api        3 (2 confirmed)

Top rules:
  sql_injection_param           5
  jwt_alg_none_accepted         3
  none_input_guard_missing      3

Recent activity (last 10 log lines): tail of learnings.log
```

## Hard rules

- Read-only by default. Mutations require explicit subcommand.
- Never delete `learnings.log` — only the JSON snapshot is renamed by `clear`.
- Never operate on a `learnings.json` with `version != "1.0"`. Print: `Schema mismatch — refusing to touch.`
- All writes are atomic (`*.tmp` + `mv`).
- `dismiss` is irreversible from this command. Manual revert: edit `learnings.json` directly.

## Reference

- `reference/learnings-schema.md` — file layout, allowed enums, validation
- `reference/learnings-promotion.md` — tier transitions, decay rules
