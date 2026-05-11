"""Pre-dispatch learnings validator.

Replaces qa-learnings-validator LLM agent. Pure deterministic — load
learnings.json, demote stale entries, drop aged-out entries, return priors
slices for each category. Read-mostly: writes only when entries demote/reset/drop.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CATEGORIES = ("unit", "api", "ui", "security", "a11y", "contract")
LEARNINGS_VERSION = "1.0"


def _now_iso(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _file_sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, FileNotFoundError):
        return None


def _age_days(now_iso: str, last_seen: str | None) -> float:
    n = _parse_iso(now_iso)
    s = _parse_iso(last_seen)
    if n is None or s is None:
        return 0.0
    return (n - s).total_seconds() / 86400.0


def _project_prior(entry: dict) -> dict:
    return {
        "id":          entry.get("id"),
        "rule":        entry.get("rule"),
        "module_path": entry.get("module_path"),
        "line_range":  entry.get("line_range"),
        "tier":        entry.get("tier"),
        "test_path":   entry.get("test_path"),
    }


def validate_learnings(
    project_root: str | Path,
    categories_enabled: tuple[str, ...] = CATEGORIES,
    now: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run validation; return {status, priors, flaky_priors, actions, log_path}.

    Side effects:
    - Atomic-rewrites learnings.json when entries are demoted/dropped/reset.
    - Appends one JSONL line per action to learnings.log.
    """
    pr = Path(project_root)
    lj_path = pr / ".qa-skills" / "learnings.json"
    log_path = pr / ".qa-skills" / "learnings.log"
    now_iso = _now_iso(now)

    empty_priors = {c: [] for c in CATEGORIES}

    if not lj_path.exists():
        return {"agent": "qa-learnings-validator", "status": "no_learnings",
                "priors": empty_priors, "flaky_priors": [], "actions": {}, "log_path": None}

    try:
        data = json.loads(lj_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"agent": "qa-learnings-validator", "status": "error",
                "priors": empty_priors, "flaky_priors": [], "actions": {},
                "reason": f"unreadable:{type(e).__name__}", "log_path": None}

    if data.get("version") != LEARNINGS_VERSION:
        return {"agent": "qa-learnings-validator", "status": "no_learnings",
                "priors": empty_priors, "flaky_priors": [], "actions": {},
                "reason": f"version_mismatch:{data.get('version')}", "log_path": None}

    actions = {"demoted": [], "dropped": [], "reset": [],
               "filtered_dismissed": 0, "filtered_unknown_module": 0}
    log_lines: list[dict] = []
    priors: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    flaky_priors: list[dict] = []
    mutated = False

    # vuln_patterns
    surviving: list[dict] = []
    for entry in data.get("vuln_patterns", []) or []:
        ent_id = entry.get("id", "<no-id>")
        user_status = entry.get("user_status", "open")

        if user_status == "dismissed_intentional":
            actions["filtered_dismissed"] += 1
            surviving.append(entry)
            continue

        module_path = entry.get("module_path", "")
        full_module = pr / module_path if module_path else None
        if not full_module or not full_module.exists():
            actions["filtered_unknown_module"] += 1
            log_lines.append({"ts": now_iso, "action": "drop", "id": ent_id,
                              "reason": "module_path_gone", "run": run_id})
            mutated = True
            continue

        # hash check + demotion / reset
        new_hash = _file_sha256(full_module)
        if new_hash and new_hash != entry.get("module_hash"):
            tier = entry.get("tier")
            old_hash = entry.get("module_hash") or ""
            entry["module_hash"] = new_hash
            entry["occurrences"] = 0
            entry["evidence_runs"] = []
            mutated = True
            if tier == "confirmed":
                entry["tier"] = "candidate"
                actions["demoted"].append({"id": ent_id, "from": "confirmed",
                                           "to": "candidate", "trigger": "module_hash_changed"})
                log_lines.append({"ts": now_iso, "action": "demote", "id": ent_id,
                                  "from": "confirmed", "to": "candidate",
                                  "trigger": "module_hash_changed",
                                  "old_hash": old_hash[:8], "new_hash": new_hash[:8],
                                  "run": run_id})
            else:
                actions["reset"].append({"id": ent_id, "trigger": "module_hash_changed"})
                log_lines.append({"ts": now_iso, "action": "reset", "id": ent_id,
                                  "trigger": "module_hash_changed", "run": run_id})

        # decay
        if user_status not in ("accepted", "dismissed_intentional"):
            age = _age_days(now_iso, entry.get("last_seen"))
            occurrences = entry.get("occurrences", 0)
            evidence_runs = entry.get("evidence_runs", []) or []
            if entry.get("tier") == "candidate" and occurrences <= 1 and len(evidence_runs) >= 5:
                actions["dropped"].append({"id": ent_id, "reason": "stale_candidate"})
                log_lines.append({"ts": now_iso, "action": "drop", "id": ent_id,
                                  "reason": "stale_candidate", "run": run_id})
                mutated = True
                continue
            if age >= 90:
                actions["dropped"].append({"id": ent_id, "reason": "aged_out", "age_days": int(age)})
                log_lines.append({"ts": now_iso, "action": "drop", "id": ent_id,
                                  "reason": "aged_out", "age_days": int(age), "run": run_id})
                mutated = True
                continue

        surviving.append(entry)

        # project prior into category slice
        if user_status in ("open", "accepted"):
            cat = entry.get("category")
            if cat in priors and cat in categories_enabled:
                priors[cat].append(_project_prior(entry))

    if mutated:
        data["vuln_patterns"] = surviving

    # flaky_history → flaky_priors
    flaky_surviving: list[dict] = []
    for entry in data.get("flaky_history", []) or []:
        ent_id = entry.get("id", "<no-id>")
        user_status = entry.get("user_status", "open")
        if user_status == "dismissed_intentional":
            flaky_surviving.append(entry)
            continue

        test_path = entry.get("test_path", "")
        test_file = test_path.split("::")[0] if test_path else ""
        if not test_file or not (pr / test_file).exists():
            log_lines.append({"ts": now_iso, "action": "drop", "id": ent_id,
                              "reason": "test_path_gone", "run": run_id})
            mutated = True
            continue
        age = _age_days(now_iso, entry.get("last_seen"))
        if age >= 90:
            log_lines.append({"ts": now_iso, "action": "drop", "id": ent_id,
                              "reason": "aged_out", "age_days": int(age), "run": run_id})
            mutated = True
            continue

        flaky_surviving.append(entry)
        flaky_priors.append({
            "id": ent_id,
            "test_path": test_path,
            "flake_count": entry.get("flake_count", 0),
            "user_status": user_status,
        })

    if mutated:
        data["flaky_history"] = flaky_surviving
        data["last_updated"] = now_iso
        data["runs_seen"] = int(data.get("runs_seen", 0)) + 1
        # atomic write
        tmp = lj_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(lj_path)

    if log_lines:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            for line in log_lines:
                f.write(json.dumps(line) + "\n")

    return {
        "agent": "qa-learnings-validator",
        "status": "completed",
        "priors": priors,
        "flaky_priors": flaky_priors,
        "actions": actions,
        "log_path": str(log_path) if log_lines else None,
    }


__all__ = ["validate_learnings", "CATEGORIES", "LEARNINGS_VERSION"]


# CLI wrapper: skills/_shared/scripts/learnings.py
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(prog="qa_skills.learnings")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--now", default=None)
    args = parser.parse_args()

    result = validate_learnings(args.project_root, run_id=args.run_id, now=args.now)
    print(json.dumps(result, indent=2))
