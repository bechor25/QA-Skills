---
name: git-diff-analyzer
description: >
  Internal skill — classifies per-module change severity using git diff and AST-level
  signature comparison. Invoked by test-orchestrator between code-analyzer and state check.
  Result adds `diff_class` to each module, allowing orchestrator to skip trivial changes.

  Standalone use: "what changed in my code since last commit", "show me semantic changes".
  Hebrew: "מה השתנה בקוד שלי", "הצג שינויים משמעותיים מאז הcommit האחרון".
---

# git-diff-analyzer

Classifies change severity per module to avoid regenerating tests for trivial edits.

## Inputs

Receives `RunContext`. Fields used:
- `project_root`
- `analysis.modules` (from code-analyzer)
- `language`

## Output

Returns updated `analysis.modules` where each module gains:
```json
{
  "diff_class": "signature_changed | body_changed | trivial | unchanged | unknown"
}
```

`diff_class` meanings:
- `signature_changed`: function names, param counts, route methods/paths, or decorators changed → regenerate full test file
- `body_changed`: implementation changed but signatures stable → regenerate only failing tests
- `trivial`: only comments, whitespace, or string literals changed → skip test update
- `unchanged`: file hash matches HEAD~1 → skip
- `unknown`: git not available or parsing failed → fallback to hash comparison

---

## Phase 1 — Git availability check

```python
import subprocess, os

def git_available(project_root: str) -> bool:
    git_dir = os.path.join(project_root, ".git")
    if not os.path.isdir(git_dir):
        return False
    result = subprocess.run(["git", "rev-parse", "HEAD"],
                            capture_output=True, cwd=project_root, timeout=5)
    return result.returncode == 0

def has_prior_commit(project_root: str) -> bool:
    result = subprocess.run(["git", "rev-parse", "HEAD~1"],
                            capture_output=True, cwd=project_root, timeout=5)
    return result.returncode == 0
```

If git not available or no prior commit: set `diff_class = "unknown"` for all modules and return.

---

## Phase 2 — Get diff per file

```python
def get_file_diff(project_root: str, file_path: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--unified=0", "HEAD~1", "HEAD", "--", file_path],
        capture_output=True, text=True, cwd=project_root, timeout=10
    )
    return result.stdout if result.returncode == 0 else ""
```

---

## Phase 3 — Classify diff

For each module in `analysis.modules`:

```python
def classify_diff(diff: str, language: str, module_path: str) -> str:
    if not diff:
        return "unchanged"

    lines_added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    lines_removed = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    all_changed = lines_added + lines_removed

    # Strip comment-only and whitespace-only lines
    non_trivial = [l for l in all_changed if not is_trivial_line(l, language)]
    if not non_trivial:
        return "trivial"

    # Check for signature changes
    if has_signature_change(non_trivial, language):
        return "signature_changed"

    return "body_changed"


def is_trivial_line(line: str, language: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    # Single-line comments
    comment_prefixes = {
        "typescript": ("//", "/*", "*"),
        "javascript": ("//", "/*", "*"),
        "python":     ("#",),
        "java":       ("//", "/*", "*"),
        "kotlin":     ("//", "/*", "*"),
        "csharp":     ("//", "/*", "*"),
    }
    prefixes = comment_prefixes.get(language, ("//", "#"))
    for p in prefixes:
        if stripped.startswith(p):
            return True
    return False


def has_signature_change(lines: list, language: str) -> bool:
    SIGNATURE_PATTERNS = {
        "typescript": [
            r"^(export\s+)?(async\s+)?function\s+\w+",
            r"^(export\s+)?class\s+\w+",
            r"router\.(get|post|put|patch|delete)\(",
            r"@(Get|Post|Put|Patch|Delete)\(",
        ],
        "python": [
            r"^def\s+\w+",
            r"^class\s+\w+",
            r"@(app|router)\.(get|post|put|patch|delete)\(",
        ],
        "java": [
            r"public\s+(static\s+)?\w+\s+\w+\s*\(",
            r"public\s+class\s+\w+",
            r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)",
        ],
        "csharp": [
            r"public\s+(async\s+)?\w+\s+\w+\s*\(",
            r"public\s+class\s+\w+",
            r"\[Http(Get|Post|Put|Delete|Patch)",
        ],
    }
    import re
    patterns = SIGNATURE_PATTERNS.get(language, [])
    for line in lines:
        for pattern in patterns:
            if re.search(pattern, line):
                return True
    return False
```

---

## Phase 4 — Apply and return

```python
def run(context: dict) -> dict:
    project_root = context["project_root"]
    language = context.get("language", "python")
    analysis = context.get("analysis", {})
    modules = analysis.get("modules", [])

    if not git_available(project_root) or not has_prior_commit(project_root):
        for m in modules:
            m["diff_class"] = "unknown"
        return analysis

    for module in modules:
        diff = get_file_diff(project_root, module["path"])
        module["diff_class"] = classify_diff(diff, language, module["path"])

    analysis["modules"] = modules
    return analysis
```

---

## Fallback behavior

If any git command times out or fails for a specific file: set `diff_class = "unknown"` for that module only. Log to `logs_dir`. Continue with remaining modules.

---

## How orchestrator uses diff_class

```python
# Phase 2 in test-orchestrator — state check extension
for module in analysis["modules"]:
    dc = module.get("diff_class", "unknown")
    if dc == "unchanged":
        # skip completely
    elif dc == "trivial":
        # skip test regeneration, keep existing tests
    elif dc in ("body_changed", "unknown"):
        # re-run tests; fix only failing ones
    elif dc == "signature_changed":
        # delete old test file for this module; regenerate from scratch
```
