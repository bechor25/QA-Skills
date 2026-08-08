---
applyTo: "skills/**,agents/**"
---

# Skill and sub-agent authoring rules

These Markdown files are the plugin's user-facing surface. Frontmatter for every installed
skill is loaded into **every** session, so oversized metadata taxes each conversation.

## Budgets

- Frontmatter: **under ~100 tokens** (roughly 400 characters of `name` + `description`).
- Body: **under ~5000 tokens**, and preferably under 300 lines, because a long body loaded
  at once defeats progressive disclosure and floods the context window.
- Tables over 20 data rows and long step-by-step procedures belong in
  `skills/<name>/references/*.md`, linked from the body and read on demand.

Check with `scripts/hooks/check-skill-budgets.sh` after editing, so a budget regression is
caught before commit rather than by an audit.

## Descriptions

Start with an action verb (`Drives…`, `Heals…`, `Scans…`, `Opens…`) and include an explicit
`Use when …` trigger clause, because discovery is what decides whether the skill is ever
loaded. Keep the English and Hebrew trigger phrases in sync — dropping one language silently
removes the trigger for those users.

## Sub-agents (`agents/*.md`)

- Each agent reads state files and writes **only** its own scoped artifact, so parallel
  fan-out stays collision-free.
- State the exact output path and schema in the agent body.
- Never instruct an agent to spawn another agent, because Claude Code forbids recursive
  sub-agent dispatch and the call will fail at runtime.
- Resolve every asset path through `${CLAUDE_PLUGIN_ROOT}`, since the plugin is installed
  outside the user's project.
