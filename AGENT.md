# Trigger phrases

The `test-orchestrator` skill activates on these phrases (case-insensitive):

## English

- `run qa`
- `qa run`
- `generate tests`
- `generate tests for my project`
- `full qa run`

## Hebrew

- `הרץ qa`
- `הרץ בדיקות`
- `צור בדיקות`
- `צור בדיקות לפרויקט שלי`

## Other skills

| Skill | English | Hebrew |
|---|---|---|
| `analyze-project` | `analyze project` | `נתח פרויקט` |
| `rerun` | `rerun tests` | `הרץ שוב` |
| `view-report` | `open qa report` | `פתח דוח qa` |
| `test-fixer` | `heal tests` / `fix the tests` / `improve test quality` | `תקן בדיקות` / `שפר איכות בדיקות` |

## Orchestration note

`test-orchestrator` is the top-level user-facing entry point. It drives the
pipeline through `qa-agent` CLI commands and LLM sub-agents for the scoped
authoring phases.

`test-fixer` is a second top-level entry point that runs **after** a
completed `test-orchestrator` run. It drives the heal loop
(`heal-diagnose` / `heal-apply` / `heal-rerun` / `heal-status`) and fans
out the `qa-ops-diagnostician` (shared fixes) and `qa-test-fixer`
(per-test residue) sub-agents.
