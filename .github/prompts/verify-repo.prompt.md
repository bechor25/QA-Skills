---
mode: agent
description: Run the full verification gate (pytest + skill budgets) and report the real output as evidence.
---

Run this repository's complete verification gate and report exactly what happened.

1. Install if needed: `pip install -e '.[parsing,dev]'` (or `scripts/setup.sh`).
2. Run `pytest qa_agent/tests`.
3. Run `bash scripts/hooks/check-skill-budgets.sh`.
4. If either fails, fix the cause and re-run from step 2, iterating until both are clean —
   a red suite means the state contract is broken somewhere downstream.
5. Report the pytest summary line verbatim plus the budget-check table as evidence.

Never describe a failing run as "mostly passing"; print the counts as they appear.
