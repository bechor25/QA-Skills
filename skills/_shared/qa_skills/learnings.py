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


SOURCE_WEIGHTS = {
    "qa-flaky-detector": 1.0,
    "qa-security-test":  0.9,
    "qa-api-test":       0.9,
    "qa-unit-test":      0.9,
    "qa-contract-test":  0.85,
    "qa-a11y-test":      0.8,
    "qa-ui-test":        0.8,
    "qa-code-analyzer":  0.4,
}

CATEGORY_TO_AGENT = {
    "unit":     "qa-unit-test",
    "api":      "qa-api-test",
    "ui":       "qa-ui-test",
    "security": "qa-security-test",
    "a11y":     "qa-a11y-test",
    "contract": "qa-contract-test",
}

PROMOTION_THRESHOLD = 3


def _sha256(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _project_id(project_root: Path) -> str:
    return hashlib.sha256(str(project_root.resolve()).encode("utf-8")).hexdigest()


def _empty_skeleton(project_root: Path, now_iso_str: str) -> dict:
    return {
        "version":     LEARNINGS_VERSION,
        "project_id":  _project_id(project_root),
        "created_at":  now_iso_str,
        "last_updated": now_iso_str,
        "runs_seen":   0,
        "vuln_patterns":          [],
        "flaky_history":          [],
        "skip_history":           [],
        "category_effectiveness": {},
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _append_log_lines(log_path: Path, lines: list[dict]) -> None:
    if not lines:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _iter_vuln_candidates(all_test_outputs: list[dict]):
    """Yield (source_agent, finding_dict) for every vulnerability reported."""
    for agent_out in all_test_outputs or []:
        if not isinstance(agent_out, dict):
            continue
        source_agent = agent_out.get("agent") or ""
        for entry in agent_out.get("outputs", []) or []:
            if not isinstance(entry, dict):
                continue
            for v in entry.get("vulnerabilities_found", []) or []:
                if isinstance(v, dict):
                    yield source_agent, v


def persist_learnings(
    project_root: str | Path,
    *,
    all_test_outputs: list[dict],
    flaky_tests: list[dict] | None = None,
    run_id: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Persist learnings.json + append learnings.log; return a summary.

    Two sources, never mixed:
      - vuln_patterns: agent outputs' `vulnerabilities_found[]`
      - flaky_history: orchestrator-level `flaky_tests[]`

    Skeleton is created on first run. All writes are atomic.

    Returns:
      {
        "vuln_patterns_total": int,
        "added_this_run":      int,
        "incremented_this_run":int,
        "promoted_this_run":   int,
        "rejected_this_run":   int,   # currently 0 (no validation step yet)
        "log_path":            str | None,
      }
    """
    pr = Path(project_root).resolve()
    lj_path  = pr / ".qa-skills" / "learnings.json"
    log_path = pr / ".qa-skills" / "learnings.log"
    now_str  = _now_iso(now)

    # Load or create skeleton.
    if lj_path.exists():
        try:
            data = json.loads(lj_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = _empty_skeleton(pr, now_str)
        if data.get("version") != LEARNINGS_VERSION:
            data = _empty_skeleton(pr, now_str)
    else:
        data = _empty_skeleton(pr, now_str)

    data.setdefault("vuln_patterns", [])
    data.setdefault("flaky_history", [])
    data.setdefault("category_effectiveness", {})

    added = incremented = promoted = 0
    log_lines: list[dict] = []

    by_id = {e.get("id"): e for e in data["vuln_patterns"] if isinstance(e, dict)}

    for source_agent, finding in _iter_vuln_candidates(all_test_outputs):
        category    = finding.get("category") or ""
        module_path = finding.get("module_path") or ""
        rule        = finding.get("rule") or ""
        if not (category and module_path and rule):
            continue
        fid = _sha256(category, module_path, rule)
        existing = by_id.get(fid)
        weight = SOURCE_WEIGHTS.get(source_agent, 0.0)

        if existing is None:
            new_entry = dict(finding)
            new_entry.update({
                "id":             fid,
                "tier":           "candidate",
                "occurrences":    1,
                "first_seen":     now_str,
                "last_seen":      now_str,
                "user_status":    "open",
                "dismiss_reason": None,
                "evidence_runs":  [run_id],
                "source_agent":   source_agent,
                "source_weight":  weight,
            })
            data["vuln_patterns"].append(new_entry)
            by_id[fid] = new_entry
            added += 1
            log_lines.append({"ts": now_str, "action": "add", "id": fid, "run": run_id})
            continue

        if existing.get("user_status") == "dismissed_intentional":
            continue
        existing["occurrences"]  = int(existing.get("occurrences", 0)) + 1
        existing["last_seen"]    = now_str
        if "line_range" in finding:
            existing["line_range"] = finding["line_range"]
        if "test_path" in finding:
            existing["test_path"]  = finding["test_path"]
        if "module_hash" in finding:
            existing["module_hash"] = finding["module_hash"]
        runs = existing.setdefault("evidence_runs", [])
        if run_id not in runs:
            runs.append(run_id)
        incremented += 1
        log_lines.append({"ts": now_str, "action": "increment", "id": fid, "run": run_id})

        if (existing.get("tier") == "candidate"
                and existing["occurrences"] >= PROMOTION_THRESHOLD):
            existing["tier"] = "confirmed"
            promoted += 1
            log_lines.append({"ts": now_str, "action": "promote", "id": fid, "run": run_id})

    # Flaky history.
    by_flaky_id = {e.get("id"): e for e in data["flaky_history"] if isinstance(e, dict)}
    for flake in flaky_tests or []:
        if not isinstance(flake, dict):
            continue
        tp = flake.get("test_path") or ""
        if not tp:
            continue
        fid = _sha256(tp)
        existing = by_flaky_id.get(fid)
        if existing is None:
            data["flaky_history"].append({
                "id":             fid,
                "test_path":      tp,
                "flake_count":    int(flake.get("flake_count", 1)),
                "first_seen":     now_str,
                "last_seen":      now_str,
                "runs_observed":  [run_id],
            })
            log_lines.append({"ts": now_str, "action": "flaky_add", "id": fid, "run": run_id})
        else:
            existing["flake_count"] = int(existing.get("flake_count", 0)) + int(flake.get("flake_count", 1))
            existing["last_seen"]   = now_str
            runs = existing.setdefault("runs_observed", [])
            if run_id not in runs:
                runs.append(run_id)
            log_lines.append({"ts": now_str, "action": "flaky_increment", "id": fid, "run": run_id})

    # category_effectiveness — per-category generation / retention ratio.
    for cat, agent in CATEGORY_TO_AGENT.items():
        agent_out = next(
            (o for o in (all_test_outputs or []) if isinstance(o, dict)
             and o.get("agent") == agent),
            None,
        )
        gen = 0
        if agent_out:
            for spec in agent_out.get("outputs", []) or []:
                if isinstance(spec, dict):
                    gen += int(spec.get("tests_written", 0) or 0)
        kept = sum(
            1 for e in data["vuln_patterns"]
            if isinstance(e, dict)
               and e.get("category") == cat
               and e.get("user_status") in ("open", "accepted")
        )
        data["category_effectiveness"][cat] = {
            "generated": gen,
            "kept":      kept,
            "ratio":     (kept / gen) if gen else 0.0,
        }

    data["last_updated"] = now_str
    data["runs_seen"]    = int(data.get("runs_seen", 0)) + 1

    _atomic_write_json(lj_path, data)
    _append_log_lines(log_path, log_lines)

    return {
        "vuln_patterns_total":  len(data["vuln_patterns"]),
        "added_this_run":       added,
        "incremented_this_run": incremented,
        "promoted_this_run":    promoted,
        "rejected_this_run":    0,
        "log_path":             str(log_path) if log_lines else None,
    }


__all__ = [
    "validate_learnings",
    "persist_learnings",
    "CATEGORIES",
    "CATEGORY_TO_AGENT",
    "LEARNINGS_VERSION",
    "PROMOTION_THRESHOLD",
    "SOURCE_WEIGHTS",
]


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
