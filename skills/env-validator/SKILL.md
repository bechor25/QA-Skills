---
name: env-validator
description: >
  Internal skill — validates environment readiness before any test generation begins.
  Always invoked by test-orchestrator after code-analyzer, before generators.
  Never runs tests — only checks preconditions and removes unavailable categories.

  English triggers (standalone): "check my environment", "validate setup", "is my project ready for tests".
  Hebrew triggers (עברית): "בדוק את הסביבה שלי", "האם הפרויקט מוכן לבדיקות", "בדוק הגדרות".
---

# env-validator

Validates environment readiness before dispatching test generators.
Modifies `RunContext.categories_enabled` by removing categories whose prerequisites are missing.

## Inputs

Receives `RunContext`. Key fields used:
- `project_root`
- `language`
- `categories_enabled`
- `user_locale`
- `checkpoint_dir`

## Output

Writes `{checkpoint_dir}/env.json`:
```json
{
  "run_id": "...",
  "checked_at": "ISO_TIMESTAMP",
  "checks": [
    { "name": "toolchain", "status": "pass|warn|fail", "detail": "...", "action": "..." }
  ],
  "categories_removed": ["ui", "api"],
  "categories_remaining": ["unit", "security"]
}
```

Print each check result using `get_message()` from `skills/_shared/validate.py`.

---

## Checks

Run all checks in this order. Each check produces `pass`, `warn`, or `fail`.

### 1. Toolchain present

Detect required tool by language:
```python
import subprocess

TOOLS = {
    "typescript": ("node", ["node", "-v"]),
    "javascript": ("node", ["node", "-v"]),
    "python":     ("python3", ["python3", "--version"]),
    "java":       ("mvn", ["mvn", "-v"]),
    "kotlin":     ("mvn", ["mvn", "-v"]),
    "csharp":     ("dotnet", ["dotnet", "--version"]),
}

tool_name, cmd = TOOLS.get(language, (None, None))
if cmd:
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode != 0:
        status = "fail"
        action = f"Install {tool_name}: https://nodejs.org / https://python.org / etc."
    else:
        status = "pass"
```

On `fail`: stop run. Print `env_toolchain_missing` message. Do not continue.

### 2. Test framework installed

Check by language:

**TypeScript/JavaScript** — read `package.json`:
```python
import json, os
pkg_path = os.path.join(project_root, "package.json")
if not os.path.exists(pkg_path):
    framework_status = "warn"
    framework_name = "jest (default)"
else:
    pkg = json.load(open(pkg_path))
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "jest" in all_deps:
        framework_status, framework_name = "pass", "jest"
    elif "vitest" in all_deps:
        framework_status, framework_name = "pass", "vitest"
    else:
        framework_status, framework_name = "warn", "jest"
```

**Python** — check `requirements.txt` / `pyproject.toml` for `pytest`:
```python
req_path = os.path.join(project_root, "requirements.txt")
if os.path.exists(req_path):
    reqs = open(req_path).read().lower()
    framework_status = "pass" if "pytest" in reqs else "warn"
    framework_name = "pytest"
```

**Java** — check `pom.xml` for `junit-jupiter`.
**C#** — check `*.csproj` for `nunit` / `xunit`.

On `warn`: print `env_framework_missing` message and ask user YES/NO.
- If user says YES: print install command (`npm i -D jest ts-jest @types/jest` etc.) — do NOT run it automatically.
- If user says NO or no response: keep the category but note framework may be missing.

### 3. App startable (only if `ui` or `api` in categories_enabled)

Detect start command from `package.json` scripts.start / `Procfile` / `uvicorn` / etc.
Parse configured `baseURL` from `playwright.config.ts` or use default (port 3000 / 8000).

```python
import socket, time, subprocess

def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=2):
            return True
    except OSError:
        return False

if not port_open(target_port):
    # Try to start the app
    start_cmd = detect_start_command(project_root, language)
    if start_cmd:
        proc = subprocess.Popen(start_cmd, shell=True, cwd=project_root,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(15):
            time.sleep(2)
            if port_open(target_port):
                break
        else:
            proc.terminate()
            status = "warn"
            action = "ui and api"  # categories to remove
    else:
        status = "warn"
```

On `warn` (server unreachable): print `env_server_unreachable`. Remove `ui` and `api` from `categories_enabled`.

### 4. DB reachable (only if `security` in categories_enabled)

Parse connection string from `.env` file if it exists:
```python
def find_env_file(root: str) -> dict:
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return {}
    vals = {}
    for line in open(path):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            vals[k.strip()] = v.strip().strip('"\'')
    return vals
```

If `DATABASE_URL` / `DB_HOST` found: attempt connection with 5s timeout.
On failure: print `env_db_unreachable`. Do NOT remove `security` — DB tests are a subset; skip only DB-specific ones.

### 5. Disk space check

```python
import shutil
usage = shutil.disk_usage(project_root)
free_mb = usage.free / (1024 * 1024)
if free_mb < 500:
    status = "fail"
    # Stop run — print env_disk_low
```

### 6. Port conflict check (only if ui in categories_enabled)

Same `port_open()` from check 3 but before attempting to start the server.
If port in use and we did not start the server: print `env_port_conflict`.

### 7. Existing test directory conflict

If `{project_root}/tests/` exists and contains test files from a DIFFERENT framework
(e.g. project uses vitest but we detect jest-style tests), print `env_tests_exist`.
Ask user: "Extend / Replace / New directory?" (default: Extend).

---

## Running the checks

```python
import datetime, json, os, uuid

def run(context: dict) -> dict:
    project_root = context["project_root"]
    language = context["language"]
    locale = context.get("user_locale", "en")
    categories = list(context.get("categories_enabled", []))
    checkpoint_dir = context.get("checkpoint_dir", os.path.join(project_root, ".qa-skills", "checkpoints"))
    os.makedirs(checkpoint_dir, exist_ok=True)

    checks = []
    categories_removed = []

    # Run each check, collect results
    # ... (implement each check as function returning {name, status, detail, action})

    # Remove categories whose checks failed
    for check in checks:
        if check["status"] in ("fail", "warn") and check.get("removes_category"):
            cat = check["removes_category"]
            if cat in categories:
                categories.remove(cat)
                categories_removed.append(cat)

    result = {
        "run_id": context["run_id"],
        "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
        "checks": checks,
        "categories_removed": categories_removed,
        "categories_remaining": categories
    }

    with open(os.path.join(checkpoint_dir, "env.json"), "w") as f:
        json.dump(result, f, indent=2)

    return result
```

Orchestrator reads `categories_remaining` and updates `RunContext.categories_enabled` before proceeding.

---

## Error handling

- Any check that raises an exception: mark `status: "warn"`, log to `logs_dir`, continue.
- Never abort the full run due to a non-fatal env check.
- Fatal checks (toolchain missing, disk full): print message and return immediately with `categories_remaining: []`.

---

## Output for orchestrator

Return `env_report` dict (same as written to disk). Orchestrator replaces `categories_enabled` with `env_report.categories_remaining`.
