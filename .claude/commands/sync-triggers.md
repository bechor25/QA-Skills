---
description: Check and repair English/Hebrew trigger parity across skills, AGENTS.md, and the plugin manifest.
---

Skills in this plugin are bilingual. A trigger that exists in only one language silently
removes the skill for those users, so audit and repair parity.

1. Collect every trigger phrase from the `description` frontmatter of each
   `skills/*/SKILL.md`.
2. Compare against the trigger table in `AGENTS.md`.
3. Report mismatches as a table: `skill | English-only | Hebrew-only | in AGENTS.md?`.
4. Fix by adding the missing counterpart — translate the intent, not the words, because the
   Hebrew phrase must be what an Israeli developer would actually type.
5. Keep frontmatter under ~100 tokens while doing it; if adding a trigger would blow the
   budget, drop the least-distinctive existing phrase instead of growing the description.
6. Verify with `scripts/hooks/check-skill-budgets.sh` and show the output.

Also check `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` descriptions
still match the skills they advertise.
