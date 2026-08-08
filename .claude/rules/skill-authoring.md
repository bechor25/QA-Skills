# Rule: skill & sub-agent authoring (`skills/`, `agents/`)

- Frontmatter under ~100 tokens, body under ~5000 tokens and ideally under 300 lines,
  because frontmatter loads in every session and a huge body defeats progressive disclosure.
- Move tables over 20 rows and long procedures into `skills/<name>/references/*.md` and link
  them from the body.
- Descriptions start with an action verb and carry an explicit `Use when …` clause, since
  discoverability decides whether the skill is ever loaded.
- Keep English and Hebrew triggers in sync — dropping one language removes the trigger for
  those users entirely.
- Sub-agents write only their own scoped artifact and never spawn other agents, because
  Claude Code forbids recursive sub-agent dispatch.
- Resolve asset paths through `${CLAUDE_PLUGIN_ROOT}`.
- Verify with `scripts/hooks/check-skill-budgets.sh`.

Full version: `.github/instructions/skills-and-agents.instructions.md`.
