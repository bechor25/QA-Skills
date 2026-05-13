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

## Orchestration note

`test-orchestrator` is the top-level user-facing entry point. It drives the
pipeline through `qa-agent` CLI commands and LLM sub-agents for the scoped
authoring phases.
