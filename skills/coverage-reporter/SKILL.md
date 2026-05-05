---
name: coverage-reporter
description: >
  Internal shared skill — aggregates test generation results into report-data.json. Standalone
  entry point — delegates to qa-coverage-reporter agent. Not intended for direct user invocation.

  Standalone use (rare): "show me my test coverage report", "aggregate test results",
  "what's my coverage breakdown". Hebrew: "הצג דוח כיסוי בדיקות", "כמה כיסוי יש לי".
---

# coverage-reporter (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-coverage-reporter` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Locate `analysis.json`, latest `test-state.json`, any prior test outputs.
4. Invoke `qa-skills:qa-coverage-reporter` agent with full inputs (analysis path, test_outputs, state, flaky_tests, quality_score, run_type, timeline, locale).
5. Display the agent's `coverage_by_category` summary and HTML report path.

The agent owns aggregation, gap detection, and html-reporter dispatch.
