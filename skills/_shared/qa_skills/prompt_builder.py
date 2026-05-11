"""Per-file prompt builder for test-gen sub-agents.

The driver invokes each test-gen sub-agent once per `expected_file` with a
**bounded** JSON payload. This module is the only place that builds those
payloads — keeps shape consistent across categories and enforces a hard
size cap so the LLM cannot be overwhelmed.

Public surface:

- `build_test_gen_prompt`  — for unit/api/security/contract/ui/a11y agents.
- `build_domain_analyzer_prompt` — for qa-domain-analyzer.
- `PROMPT_SIZE_CAP_CHARS`  — 4096-char limit on the serialized JSON payload.
- `PromptTooLarge`         — raised when a payload exceeds the cap.
"""

from __future__ import annotations

import json
from typing import Any, Optional

__all__ = [
    "PROMPT_SIZE_CAP_CHARS",
    "PromptTooLarge",
    "REFERENCE_BY_CATEGORY",
    "PRIOR_SUMMARY_MAX_LINES",
    "build_test_gen_prompt",
    "build_domain_analyzer_prompt",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


PROMPT_SIZE_CAP_CHARS = 4096
"""Hard cap on serialized JSON payload size.

Per-file prompts are intentionally tiny — full source files belong to the
domain_brief slice (which the analyzer pre-extracted), not the test-gen
prompt. Crossing this cap is a builder bug, not a runtime input issue.
"""

PRIOR_SUMMARY_MAX_LINES = 5
"""Maximum entries in `prior_summary` — paths only, no code."""


REFERENCE_BY_CATEGORY = {
    "unit":     "reference/unit-test-patterns.md",
    "api":      "reference/api-test-patterns.md",
    "security": "reference/security-test-patterns.md",
    "contract": "reference/contract-test-patterns.md",
    "ui":       "reference/ui-test-patterns.md",
    "a11y":     "reference/a11y-test-patterns.md",
}


class PromptTooLarge(ValueError):
    """The built prompt exceeded `PROMPT_SIZE_CAP_CHARS`.

    Carries the actual size + offending payload for debugging.
    """

    def __init__(self, size: int, payload: dict):
        super().__init__(
            f"prompt size {size} > cap {PROMPT_SIZE_CAP_CHARS}"
        )
        self.size = size
        self.payload = payload


# ---------------------------------------------------------------------------
# build_test_gen_prompt
# ---------------------------------------------------------------------------


def build_test_gen_prompt(
    *,
    agent: str,
    category: str,
    expected_file: dict,
    domain_brief: Optional[dict],
    language: str,
    project_root: str,
    run_id: str,
    prior_summary: Optional[list[str]] = None,
    server_plan: Optional[dict] = None,
    frontend_kind: Optional[str] = None,
) -> dict:
    """Build the per-file Task payload for a test-gen sub-agent.

    Returned dict is **the entire input** to the sub-agent — no orchestrator
    will pass extra fields. The shape is:

    ```
    {
      "agent":                "qa-unit-test",
      "run_id":               "...",
      "project_root":         "/abs/path",
      "language":             "typescript",
      "category":             "unit",
      "file_to_generate":     "tests/unit/auth/login.test.ts",
      "covers":               ["src/auth/login.ts"],
      "domain_brief":         { behaviors[], test_hints[], source_files[] } | null,
      "reference_pattern":    "reference/unit-test-patterns.md",
      "prior_summary":        ["tests/unit/.../jwt.test.ts", ...],   ≤5 entries
      "server_plan":          {url, ...}        ui/a11y only
      "frontend_kind":        "spa"             ui/a11y only
    }
    ```

    Raises `PromptTooLarge` if the serialized payload exceeds the cap. The
    builder never silently truncates — overflow is a contract bug.
    """
    if not isinstance(expected_file, dict):
        raise TypeError(f"expected_file must be dict, got {type(expected_file)!r}")
    file_to_generate = expected_file.get("path")
    covers = expected_file.get("covers")
    if not file_to_generate or not isinstance(covers, list):
        raise ValueError(
            f"expected_file missing required keys (path, covers): {expected_file!r}"
        )

    brief_slice = _slice_brief_for_file(domain_brief, file_to_generate)
    prior = _bound_prior(prior_summary)

    payload: dict[str, Any] = {
        "agent":             agent,
        "run_id":            run_id,
        "project_root":      project_root,
        "language":          language,
        "category":          category,
        "file_to_generate":  file_to_generate,
        "covers":            list(covers),
        "domain_brief":      brief_slice,
        "reference_pattern": REFERENCE_BY_CATEGORY.get(category, ""),
        "prior_summary":     prior,
    }

    if category in ("ui", "a11y"):
        if server_plan is not None:
            payload["server_plan"] = server_plan
        if frontend_kind is not None:
            payload["frontend_kind"] = frontend_kind

    _assert_size(payload)
    return payload


def _slice_brief_for_file(
    brief: Optional[dict], file_to_generate: str
) -> Optional[dict]:
    """Extract the brief entry for one file from the full domain_brief.

    A domain brief file has shape ``{"category": cat, "briefs": [...]}``. For
    a single-file prompt the sub-agent needs only that file's entry — passing
    siblings inflates the prompt and tempts the LLM to generate >1 file.

    Returns:
        - the matching brief entry dict, OR
        - the brief dict already addressed to that file (when caller pre-sliced), OR
        - None if no brief is available.
    """
    if brief is None:
        return None
    if not isinstance(brief, dict):
        return None

    if brief.get("expected_file") == file_to_generate:
        return brief

    briefs = brief.get("briefs")
    if isinstance(briefs, list):
        for b in briefs:
            if isinstance(b, dict) and b.get("expected_file") == file_to_generate:
                return b
    return None


def _bound_prior(prior_summary: Optional[list[str]]) -> list[str]:
    """Clamp prior_summary to PRIOR_SUMMARY_MAX_LINES path strings, no duplicates."""
    if not prior_summary:
        return []
    seen: list[str] = []
    for p in prior_summary:
        if not isinstance(p, str):
            continue
        if p in seen:
            continue
        seen.append(p)
        if len(seen) >= PRIOR_SUMMARY_MAX_LINES:
            break
    return seen


def _assert_size(payload: dict) -> None:
    """Raise PromptTooLarge if serialized JSON exceeds the cap."""
    blob = json.dumps(payload, ensure_ascii=False)
    size = len(blob)
    if size > PROMPT_SIZE_CAP_CHARS:
        raise PromptTooLarge(size, payload)


# ---------------------------------------------------------------------------
# build_domain_analyzer_prompt (echo of qa_run.phase_2_7 payload shape)
# ---------------------------------------------------------------------------


def build_domain_analyzer_prompt(
    *,
    run_id: str,
    project_root: str,
    category: str,
    language: str,
    logs_dir: str,
    chunk_path: str,
    expected_files: list[dict],
    analysis_path: str,
) -> dict:
    """Build the qa-domain-analyzer payload for one chunk.

    Same shape as `qa_run._domain_analyzer_payload`. Exposed here so test
    code can reuse the builder without depending on the qa_run module.

    Size cap applies; large chunks must be split upstream.
    """
    payload = {
        "run_id":         run_id,
        "project_root":   project_root,
        "category":       category,
        "language":       language,
        "logs_dir":       logs_dir,
        "chunk_path":     chunk_path,
        "expected_files": expected_files,
        "analysis_path":  analysis_path,
    }
    _assert_size(payload)
    return payload
