---
name: coverage-reporter
description: >
  Internal shared skill — aggregates test generation results into report-data.json, then
  invokes html-reporter. Always called automatically by test-orchestrator after all test skills
  complete. Not intended for direct user invocation.

  Standalone use (rare): "show me my test coverage report", "aggregate test results",
  "what's my coverage breakdown". Hebrew: "הצג דוח כיסוי בדיקות", "כמה כיסוי יש לי".
---

# coverage-reporter

Collects outputs from all test skills, computes coverage metrics, identifies gaps and blind spots,
writes `report-data.json`, then hands off to `html-reporter`.

## Inputs

```json
{
  "analysis": { /* full code-analyzer output */ },
  "test_outputs": [/* arrays returned by each test skill */],
  "state": { /* new test-state.json content */ },
  "run_type": "full | incremental",
  "project_root": "string",
  "timeline": [/* step timing records */]
}
```

## Phase 1 — Coverage computation

For each module in `analysis.modules`, determine status:

```python
def compute_module_status(module, all_test_outputs):
    tests_for_module = [
        t for output in all_test_outputs
        for t in output
        if t.get("source_module") == module["path"]
    ]
    
    if not tests_for_module:
        return "uncovered"
    
    total_exports = len(module.get("exports", []))
    if total_exports == 0:
        return "covered"
    
    # Estimate covered exports from test count
    # Each test file covers a portion; use heuristic
    covered_exports = min(total_exports, sum(t.get("tests_written", 0) // 2 for t in tests_for_module))
    pct = (covered_exports / total_exports) * 100
    
    if pct >= 80:
        return "covered"
    elif pct >= 40:
        return "partial"
    else:
        return "uncovered"
```

Modules whose hash was unchanged in this run get status `"unchanged"` — do not recompute.

## Phase 2 — Category coverage percentages

```python
categories = ["unit", "ui", "api", "security"]

for cat in categories:
    # Which modules are relevant to this category?
    if cat == "unit":
        relevant = [m for m in modules if m["type"] in ("service", "util", "model", "middleware")]
    elif cat == "ui":
        relevant = analysis.get("frontend_files", [])
    elif cat == "api":
        relevant = [m for m in modules if m["type"] == "controller"]
    elif cat == "security":
        relevant = [m for m in modules if m["has_auth"] or m["has_db_queries"] or m["input_fields"]]
    
    covered = len([m for m in relevant if status_map[m["path"]] in ("covered", "unchanged")])
    pct = round((covered / len(relevant)) * 100) if relevant else 0
    
    coverage_by_category[cat] = {
        "files": len(relevant),
        "covered": covered,
        "pct": pct
    }
```

## Phase 3 — Gap analysis

A **gap** is a module that is `uncovered` or `partial` with a specific explainable reason.

Assign severity:

| Condition | Severity |
|-----------|----------|
| Module has `has_auth: true` AND uncovered | high |
| Module has `has_db_queries: true` AND uncovered | high |
| Controller/route module uncovered | high |
| Service module partial | medium |
| Utility module uncovered | low |

```python
gaps = []
for module in modules:
    status = status_map[module["path"]]
    if status not in ("covered",):
        reason = derive_gap_reason(module, status)
        severity = derive_severity(module, status)
        gaps.append({
            "module": module["path"],
            "reason": reason,
            "severity": severity
        })

def derive_gap_reason(module, status):
    if status == "uncovered":
        if module["has_auth"]:
            return "Auth handler has no tests — token validation, session management, and access control untested"
        if module["has_db_queries"]:
            return "DB operations untested — no verification that queries are correct or safe from injection"
        if module["type"] == "controller":
            return "HTTP handler untested — request parsing, response format, and error codes not verified"
        return f"Module exports {len(module['exports'])} functions with no test coverage"
    elif status == "partial":
        return f"Only some exports tested — error paths and edge cases likely missing"
```

## Phase 4 — Blind spot detection

Blind spots are patterns that tests systematically miss — not just uncovered code, but
categories of behavior that are hard to think of:

```python
blind_spots = []

for module in modules:
    # Blind spot: DB-querying modules with no idempotency test
    if module["has_db_queries"] and not has_idempotency_test(module, test_outputs):
        blind_spots.append({
            "description": "No idempotency test — calling this function twice may double-write to DB",
            "module": module["path"],
            "category": "unit"
        })
    
    # Blind spot: Auth modules with no timing attack test
    if module["has_auth"] and not has_timing_test(module, test_outputs):
        blind_spots.append({
            "description": "No timing attack test — response time may leak whether user exists",
            "module": module["path"],
            "category": "security"
        })
    
    # Blind spot: Input fields with no unicode test
    if module["input_fields"] and not has_unicode_test(module, test_outputs):
        blind_spots.append({
            "description": "No Unicode/special-char input test — may break with non-ASCII user data",
            "module": module["path"],
            "category": "unit"
        })
    
    # Blind spot: Controllers with no CORS test
    if module["type"] == "controller" and not has_cors_test(module, test_outputs):
        blind_spots.append({
            "description": "No CORS header test — cross-origin access policy unverified",
            "module": module["path"],
            "category": "security"
        })
    
    # Blind spot: Async functions with no concurrent call test
    if "async" in module.get("flags", []) and not has_concurrency_test(module, test_outputs):
        blind_spots.append({
            "description": "No concurrent execution test — race condition under parallel calls undetected",
            "module": module["path"],
            "category": "unit"
        })

# Global blind spots
if analysis["stats"]["has_frontend"] and not any_loading_state_test(test_outputs):
    blind_spots.append({
        "description": "No loading state test — UI may show broken state while fetching data",
        "module": "frontend (global)",
        "category": "ui"
    })

if analysis["stats"]["has_api"] and not any_pagination_test(test_outputs):
    blind_spots.append({
        "description": "No pagination edge case test — last page and invalid page behavior unverified",
        "module": "API (global)",
        "category": "api"
    })
```

## Phase 5 — Recommendations

```python
recommendations = []
priority = 1

# Prioritize by: high-severity gaps first, then blind spots, then partial
high_gaps = [g for g in gaps if g["severity"] == "high"]
for gap in sorted(high_gaps, key=lambda g: g["module"]):
    recommendations.append({
        "priority": priority,
        "text": f"Add tests for {gap['module']}: {gap['reason']}",
        "module": gap["module"]
    })
    priority += 1

for bs in blind_spots[:5]:  # top 5 blind spots
    recommendations.append({
        "priority": priority,
        "text": f"[{bs['category'].upper()}] {bs['description']} — affects {bs['module']}",
        "module": bs["module"]
    })
    priority += 1
```

## Phase 6 — Build report-data.json

Assemble the full report object:

```python
import datetime, json

new_tests = sum(t["tests_written"] for output in test_outputs for t in output 
                if t["status"] == "created")
updated_tests = sum(t["tests_written"] for output in test_outputs for t in output 
                    if t["status"] == "updated")

report_data = {
    "project_name": os.path.basename(project_root),
    "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    "run_type": run_type,
    "summary": {
        "files_scanned": analysis["stats"]["total_files"],
        "files_with_tests": len([m for m in modules if status_map[m["path"]] != "uncovered"]),
        "new_tests_generated": new_tests,
        "tests_updated": updated_tests,
        "tests_unchanged": len([m for m in modules if status_map[m["path"]] == "unchanged"])
    },
    "coverage_by_category": coverage_by_category,
    "modules": [
        {
            "path": m["path"],
            "language": analysis["language"],
            "status": status_map[m["path"]],
            "tests_generated": [t["path"] for output in test_outputs for t in output 
                                  if t.get("source_module") == m["path"]],
            "gaps": [g["reason"] for g in gaps if g["module"] == m["path"]],
            "blind_spots": [bs["description"] for bs in blind_spots if bs["module"] == m["path"]]
        }
        for m in modules
    ],
    "gaps": gaps,
    "blind_spots": blind_spots,
    "recommendations": recommendations,
    "timeline": timeline,
    "warnings": analysis.get("warnings", [])
}

os.makedirs(f"{project_root}/test-reports", exist_ok=True)
with open(f"{project_root}/test-reports/report-data.json", "w") as f:
    json.dump(report_data, f, indent=2)
```

## Phase 7 — Hand off to html-reporter

After writing `report-data.json`, immediately invoke the `html-reporter` skill:
```
Pass: project_root, report_data (the dict, not just the path)
```

Do not print any summary to the user — `html-reporter` produces the final output.
