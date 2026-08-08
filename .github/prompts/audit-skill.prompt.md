---
mode: agent
description: Audit a SKILL.md or agents/*.md for context budgets, description quality, progressive disclosure, and EN/HE trigger parity.
---

Audit the skill or sub-agent Markdown file I name (default: every `skills/*/SKILL.md` and
`agents/*.md`).

Budgets — frontmatter loads in every session and an oversized body defeats progressive
disclosure:

- frontmatter ≤ ~100 tokens, body ≤ ~5000 tokens, body ≤ 300 lines,
- inline tables ≤ 20 data rows; anything larger belongs in `skills/<name>/references/*.md`.

Run `bash scripts/hooks/check-skill-budgets.sh` first for the mechanical numbers, then check
by hand:

1. Description starts with an action verb (`Drives`, `Heals`, `Scans`, `Opens`).
2. Description contains an explicit `Use when …` trigger clause, because discoverability
   decides whether the skill is ever loaded.
3. English and Hebrew triggers are in sync with the table in `AGENTS.md` — a one-language
   trigger removes the skill for the other audience.
4. Bodies over 300 lines have a sibling `references/` directory and link to it.
5. Sub-agents name exactly one scoped output artifact and never spawn other agents, which
   Claude Code forbids.

Report one line per finding as `<file> — <problem> → <fix>`, then apply the fixes and re-run
the budget check to show it is clean.
