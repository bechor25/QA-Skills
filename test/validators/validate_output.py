#!/usr/bin/env python3
"""
Validates outputs produced by qa-skills after a test generation run.
Usage: python validate_output.py <project_root> [--scenario <name>]

Checks:
  1. test-state.json exists and matches schema
  2. report-data.json exists and matches schema
  3. HTML report exists and has correct structure
  4. Generated test files exist (based on test-state.json entries)
  5. Scenario-specific assertions (if --scenario provided)
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCHEMAS_DIR = Path(__file__).parent / "schemas"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SKIP = "\033[93m⟳\033[0m"

failures = []
passes = []


def ok(msg):
    passes.append(msg)
    print(f"  {PASS} {msg}")


def fail(msg):
    failures.append(msg)
    print(f"  {FAIL} {msg}")


def check(condition, msg_pass, msg_fail=None):
    if condition:
        ok(msg_pass)
    else:
        fail(msg_fail or f"FAILED: {msg_pass}")


# ─── Schema validation ────────────────────────────────────────────────────────

def validate_schema(data: dict, schema_name: str) -> list[str]:
    """
    Minimal JSON Schema validator (subset: type, required, enum, minLength, minimum, maximum).
    Returns list of errors.
    """
    schema_path = SCHEMAS_DIR / schema_name
    with open(schema_path) as f:
        schema = json.load(f)
    return _validate_node(data, schema, schema.get("definitions", {}), path="$")


def _validate_node(value, schema, definitions, path):
    errors = []

    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        schema = definitions.get(ref_name, {})

    expected_type = schema.get("type")
    if expected_type:
        type_map = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict, "number": (int, float)}
        expected = type_map.get(expected_type)
        if expected and not isinstance(value, expected):
            errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
            return errors

    if expected_type == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: minLength {schema['minLength']} violated (len={len(value)})")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: maxLength {schema['maxLength']} violated (len={len(value)})")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: value '{value}' not in enum {schema['enum']}")
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected const '{schema['const']}', got '{value}'")

    if expected_type == "integer":
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value {value} > maximum {schema['maximum']}")

    if expected_type == "object":
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in value:
                errors.extend(_validate_node(value[prop], prop_schema, definitions, f"{path}.{prop}"))

    if expected_type == "array":
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(_validate_node(item, item_schema, definitions, f"{path}[{i}]"))

    return errors


# ─── Check functions ───────────────────────────────────────────────────────────

def check_test_state(project_root: Path):
    print("\n[test-state.json]")
    state_path = project_root / "test-state.json"

    if not state_path.exists():
        fail("test-state.json not found")
        return None

    with open(state_path) as f:
        state = json.load(f)

    ok("test-state.json exists")

    errors = validate_schema(state, "test-state.schema.json")
    if errors:
        for e in errors:
            fail(f"Schema: {e}")
    else:
        ok("Schema valid")

    check(state.get("version") == "1.0", "version == '1.0'")
    check(bool(state.get("modules")), "modules dict non-empty")

    for mod_path, mod_data in state.get("modules", {}).items():
        h = mod_data.get("hash", "")
        check(len(h) == 64, f"{mod_path}: hash is 64-char SHA-256", f"{mod_path}: bad hash '{h[:8]}...'")

    return state


def check_report_data(project_root: Path):
    print("\n[report-data.json]")
    report_dir = project_root / "test-reports"
    report_path = report_dir / "report-data.json"

    if not report_path.exists():
        fail("test-reports/report-data.json not found")
        return None

    with open(report_path) as f:
        data = json.load(f)

    ok("report-data.json exists")

    errors = validate_schema(data, "report-data.schema.json")
    if errors:
        for e in errors:
            fail(f"Schema: {e}")
    else:
        ok("Schema valid")

    # Coverage categories must all be present
    cat = data.get("coverage_by_category", {})
    for c in ["unit", "ui", "api", "security"]:
        check(c in cat, f"coverage_by_category.{c} present")
        if c in cat:
            check(0 <= cat[c].get("pct", -1) <= 100, f"{c}.pct in [0,100]")

    # Gaps must have specific (non-generic) reasons
    for gap in data.get("gaps", []):
        reason = gap.get("reason", "")
        check(len(reason) >= 10, f"gap reason is specific: '{reason[:50]}'",
              f"gap reason too short/generic: '{reason}'")

    # Timeline must include at least code-analyzer
    timeline_steps = [t["step"] for t in data.get("timeline", [])]
    check("code-analyzer" in timeline_steps, "timeline includes code-analyzer")

    return data


def check_html_report(project_root: Path):
    print("\n[HTML report]")
    report_dir = project_root / "test-reports"

    html_files = list(report_dir.glob("report-*.html")) if report_dir.exists() else []
    check(len(html_files) >= 1, f"HTML report file exists in test-reports/ ({len(html_files)} found)")

    if not html_files:
        return

    html_path = sorted(html_files)[-1]  # most recent
    content = html_path.read_text(encoding="utf-8")
    ok(f"Reading: {html_path.name}")

    check("<!DOCTYPE html>" in content or "<!doctype html>" in content.lower(), "HTML doctype present")
    check("<head>" in content, "<head> present")
    check("<body>" in content, "<body> present")

    # No external CDN
    cdn_refs = re.findall(r'(href|src)=["\']https?://', content)
    check(len(cdn_refs) == 0, "No external CDN references",
          f"External CDN refs found: {cdn_refs[:3]}")

    # No external font references
    check("fonts.googleapis.com" not in content, "No Google Fonts")

    # Four gauges
    gauge_count = content.count('stroke-dasharray')
    check(gauge_count >= 4, f"At least 4 gauge arcs present (found {gauge_count})")

    # Filter buttons
    check("filterModules" in content, "Filter JS function present")
    check("searchModules" in content, "Search JS function present")

    # Dark mode
    check("prefers-color-scheme: dark" in content, "Dark mode CSS present")

    # Blind spots section
    check("blind" in content.lower() or "Blind Spot" in content, "Blind spots section present")

    # Footer with state link
    check("test-state.json" in content, "Footer links to test-state.json")


def check_generated_test_files(project_root: Path, state: dict):
    print("\n[Generated test files]")
    if not state:
        print(f"  {SKIP} Skipping — no state to check")
        return

    all_test_paths = []
    for mod_data in state.get("modules", {}).values():
        all_test_paths.extend(mod_data.get("tests_generated", []))

    if not all_test_paths:
        fail("No test files listed in test-state.json modules")
        return

    ok(f"test-state lists {len(all_test_paths)} test file(s)")

    missing = []
    for rel_path in all_test_paths:
        full_path = project_root / rel_path
        if not full_path.exists():
            missing.append(rel_path)

    if missing:
        for m in missing:
            fail(f"Missing: {m}")
    else:
        ok(f"All {len(all_test_paths)} test files exist on disk")


def check_no_sensitive_data_in_tests(project_root: Path):
    print("\n[Sensitive data in test files]")
    test_dirs = [project_root / "tests", project_root / "src" / "test"]
    forbidden_patterns = [
        (r'passwordHash', "passwordHash field"),
        (r'password_hash', "password_hash field"),
        (r'\.salt\b', ".salt field"),
    ]
    found = []
    for test_dir in test_dirs:
        if not test_dir.exists():
            continue
        for test_file in test_dir.rglob("*"):
            if not test_file.is_file():
                continue
            if not any(test_file.suffix in [".ts", ".py", ".java", ".cs"] for _ in [1]):
                continue
            content = test_file.read_text(errors="ignore")
            for pattern, label in forbidden_patterns:
                if re.search(pattern, content):
                    # Allow passwordHash in test setup/mock — only flag in assertions
                    if re.search(r'(expect|assert|toBe|assertEqual).*' + pattern, content):
                        found.append(f"{test_file.name}: {label} in assertion")

    if found:
        for f in found:
            fail(f)
    else:
        ok("No sensitive field names in test assertions")


# ─── Scenario-specific checks ─────────────────────────────────────────────────

def check_scenario_incremental(project_root: Path, state: dict, report: dict):
    print("\n[Scenario 05: Incremental assertions]")
    if not report:
        return

    check(report.get("run_type") == "incremental", "run_type == incremental")
    summary = report.get("summary", {})
    check(summary.get("tests_unchanged", 0) > 0, "tests_unchanged > 0")
    check(summary.get("tests_updated", 0) > 0, "tests_updated > 0")

    # ui-playwright and api-test must be skipped
    timeline = {t["step"]: t for t in report.get("timeline", [])}
    if "ui-playwright" in timeline:
        check(timeline["ui-playwright"]["status"] == "skipped",
              "ui-playwright: skipped in incremental with no frontend changes")
    if "api-test" in timeline:
        check(timeline["api-test"]["status"] == "skipped",
              "api-test: skipped in incremental with no route changes")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate qa-skills output")
    parser.add_argument("project_root", help="Path to the fixture project root")
    parser.add_argument("--scenario", default=None, help="Scenario name for extra checks: incremental")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        print(f"Error: {project_root} does not exist")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f" Validating: {project_root.name}")
    print(f" Scenario:   {args.scenario or 'generic'}")
    print(f"{'='*60}")

    state = check_test_state(project_root)
    report = check_report_data(project_root)
    check_html_report(project_root)
    check_generated_test_files(project_root, state)
    check_no_sensitive_data_in_tests(project_root)

    if args.scenario == "incremental":
        check_scenario_incremental(project_root, state, report)

    print(f"\n{'='*60}")
    print(f" Results: {len(passes)} passed, {len(failures)} failed")
    print(f"{'='*60}\n")

    if failures:
        print("Failed checks:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
