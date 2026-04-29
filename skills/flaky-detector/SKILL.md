---
name: flaky-detector
description: >
  Internal skill — detects non-deterministic (flaky) tests by re-running the suite 3 times
  after all tests pass. Reports cause hypothesis and plain-language fix suggestions for each
  flaky test. Never modifies test files. Only reports.

  Standalone use: "find flaky tests", "check for unstable tests", "which tests are unreliable".
  Hebrew: "מצא בדיקות לא יציבות", "בדוק אילו בדיקות לא אמינות", "בדיקות לא דטרמיניסטיות".
---

# flaky-detector

Detects non-deterministic tests by re-running and comparing results. Reports findings only — never modifies test files.

## When to invoke

Orchestrator invokes this skill after Phase 6 (Execute & Verify) completes with all tests passing.
If tests are already failing, skip flaky detection — there's nothing to measure.

## Inputs

Receives `RunContext` plus:
- `test_outputs`: list of all test files generated this run
- Language + project_root

## Output

Adds `flaky_tests: [{path, test_name, cause_hypothesis, suggested_fix_text, run_results}]`
to the report data. Never writes to test files.

---

## Phase 1 — Re-run tests N times

```python
import subprocess, json, os

RERUN_COUNT = 3

def rerun_suite(project_root: str, language: str) -> list:
    """Run the full test suite RERUN_COUNT times. Return list of per-run results."""
    results = []
    for i in range(RERUN_COUNT):
        result = run_tests(project_root, language)
        results.append(result)
    return results
```

Use the same run command as Execute & Verify phase:
| Language | Command |
|----------|---------|
| TypeScript/JS | `npx jest --json --outputFile=.qa-skills/flaky-{i}.json 2>&1` |
| Python | `pytest --tb=no -q --json-report --json-report-file=.qa-skills/flaky-{i}.json 2>&1` |

Parse results same way as Phase 6.

---

## Phase 2 — Identify flaky tests

```python
def find_flaky(run_results: list) -> list:
    """A test is flaky if it passed in at least one run and failed in at least one other."""
    test_outcomes: dict[str, list[str]] = {}

    for run_idx, result in enumerate(run_results):
        for test in result.get("tests", []):
            key = f"{test['file']}::{test['name']}"
            test_outcomes.setdefault(key, []).append(test["outcome"])

    flaky = []
    for test_key, outcomes in test_outcomes.items():
        passed = outcomes.count("passed")
        failed = outcomes.count("failed")
        if passed > 0 and failed > 0:
            flaky.append({
                "test_key": test_key,
                "outcomes": outcomes,
                "pass_rate": f"{passed}/{len(outcomes)}"
            })

    return flaky
```

---

## Phase 3 — Cause hypothesis

For each flaky test, read the test source file and pattern-match:

```python
import re

CAUSE_PATTERNS = [
    {
        "cause": "time-dependent",
        "patterns": [r"Date\.now\(\)", r"new Date\(\)", r"datetime\.now\(\)",
                     r"time\.time\(\)", r"LocalDateTime\.now\(\)"],
        "suggestion": "Mock the clock. Use jest.useFakeTimers() / freezegun / Mockito.mockStatic(LocalDateTime.class). "
                      "Never assert on real timestamps without mocking."
    },
    {
        "cause": "non-deterministic-random",
        "patterns": [r"Math\.random\(\)", r"random\.(random|randint|choice)\(",
                     r"UUID\.randomUUID\(\)", r"uuid\.uuid4\(\)"],
        "suggestion": "Seed the random generator before the test or mock it. "
                      "Use jest.spyOn(Math, 'random').mockReturnValue(0.5) or equivalent."
    },
    {
        "cause": "network-dependent",
        "patterns": [r"fetch\(", r"axios\.", r"requests\.(get|post|put)",
                     r"httpx\.", r"RestTemplate", r"HttpClient"],
        "suggestion": "Mock the HTTP call. The test should not reach real network. "
                      "Use jest.mock('axios') / unittest.mock.patch('requests.get') / etc."
    },
    {
        "cause": "ordering-dependent",
        "patterns": [r"beforeAll\(", r"afterAll\(", r"setUpClass", r"tearDownClass"],
        "suggestion": "Test shares state across test cases. Move setup into beforeEach/setUp. "
                      "Each test must be independently runnable."
    },
    {
        "cause": "async-timing",
        "patterns": [r"setTimeout\(", r"setInterval\(", r"sleep\(", r"asyncio\.sleep\(",
                     r"Thread\.sleep\("],
        "suggestion": "Replace real time waits with mock timers or proper async awaiting. "
                      "Use jest.runAllTimers() or await the actual async operation."
    },
    {
        "cause": "file-system-state",
        "patterns": [r"fs\.(read|write|unlink)", r"open\(.*['\"]r['\"]", r"os\.path\.exists\(",
                     r"File\.", r"FileWriter"],
        "suggestion": "Test reads/writes real files and may depend on prior test state. "
                      "Use temp files (tmp_path in pytest, os.tmpfile) and clean up in teardown."
    },
]

def hypothesize_cause(test_file_path: str) -> dict:
    try:
        content = open(test_file_path).read()
    except FileNotFoundError:
        return {"cause": "unknown", "suggestion": "Could not read test file."}

    for pattern_def in CAUSE_PATTERNS:
        for pat in pattern_def["patterns"]:
            if re.search(pat, content):
                return {
                    "cause": pattern_def["cause"],
                    "suggestion": pattern_def["suggestion"]
                }

    return {
        "cause": "unknown",
        "suggestion": "No common pattern found. Check for shared module-level state, "
                      "external file dependencies, or port/socket conflicts between tests."
    }
```

---

## Phase 4 — Build report output

```python
def build_flaky_report(flaky_tests: list, project_root: str) -> list:
    report = []
    for ft in flaky_tests:
        file_path = ft["test_key"].split("::")[0]
        abs_path = os.path.join(project_root, file_path)
        hypothesis = hypothesize_cause(abs_path)

        report.append({
            "path": file_path,
            "test_name": ft["test_key"].split("::", 1)[-1] if "::" in ft["test_key"] else ft["test_key"],
            "pass_rate": ft["pass_rate"],
            "run_results": ft["outcomes"],
            "cause_hypothesis": hypothesis["cause"],
            "suggested_fix_text": hypothesis["suggestion"]
        })

        # Print user-facing message
        print(get_message("flaky_found", locale,
                          test=ft["test_key"], cause=hypothesis["cause"]))

    return report
```

---

## What humans miss

**Order-dependent tests** — run in reverse order to detect:
```python
# Additional detection: run tests in reverse alphabetical order
# If different tests fail in reversed order → ordering dependency
```

**Slow-flaky distinction** — some "flaky" tests are actually just slow:
```python
# If a test always fails on run 1 but passes on runs 2+: likely a warmup/cache issue
# Flag as "slow_start" cause, not "flaky"
```

---

## IMPORTANT: Never modify test files

The flaky-detector ONLY reads and reports. It never edits test source files.
Suggested fixes appear in the report as plain text for the tester to share with a developer.

---

## Output format (return to orchestrator)

Flaky detector does not return standard `test_output` format. Instead it returns:
```json
{
  "flaky_tests": [
    {
      "path": "tests/unit/auth/login.test.ts",
      "test_name": "loginUser returns token",
      "pass_rate": "2/3",
      "run_results": ["passed", "passed", "failed"],
      "cause_hypothesis": "time-dependent",
      "suggested_fix_text": "Mock the clock. Use jest.useFakeTimers()..."
    }
  ],
  "runs_completed": 3,
  "total_tests_checked": 42
}
```

Orchestrator merges `flaky_tests` into `report_data` and passes to html-reporter.
html-reporter shows a dedicated "Flaky Tests" section with cause + fix text.
