---
description: Run the full verification gate for this repo (pytest + skill budgets) and report evidence.
---

Run this repository's complete verification gate and report the real output — never claim a
pass you have not seen.

1. Ensure the dev environment exists:
   ```bash
   [ -d .venv ] || scripts/setup.sh
   ```
2. Run the test suite:
   ```bash
   pytest qa_agent/tests
   ```
3. Run the Markdown surface check:
   ```bash
   scripts/hooks/check-skill-budgets.sh
   ```
4. If anything fails, fix the cause and re-run from step 2. Iterate until both are clean,
   because a red suite means the state contract is broken somewhere downstream.
5. Report:
   - the pytest summary line, pasted verbatim as evidence;
   - the budget-check output;
   - a one-line verdict: `green` or the first failure with its file:line.

Do not summarize a failure as "mostly passing". Report the counts exactly as printed.
