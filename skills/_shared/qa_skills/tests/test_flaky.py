"""flaky module tests — focuses on cause-hypothesis logic (no real subprocess)."""

from __future__ import annotations

from qa_skills.flaky import _hypothesize, CAUSE_HINTS, FIX_HINTS_EN, FIX_HINTS_HE


def test_hypothesize_race_keyword():
    assert _hypothesize("test_concurrent_writes_succeed") == "race_or_shared_state"


def test_hypothesize_timing_keyword():
    assert _hypothesize("test_login_timeout_is_5s") == "timing_dependent"


def test_hypothesize_random_in_body():
    assert _hypothesize("test_id_unique", "Math.random()") == "non_deterministic_input"


def test_hypothesize_external_dep():
    assert _hypothesize("test_external_api_call") == "external_dependency"


def test_hypothesize_fallback_unknown():
    assert _hypothesize("test_normal_thing") == "unknown"


def test_cause_hint_codes_all_have_fix_hints_en():
    for code in CAUSE_HINTS:
        assert code in FIX_HINTS_EN, f"{code} missing English fix hint"


def test_cause_hint_codes_all_have_fix_hints_he():
    for code in CAUSE_HINTS:
        assert code in FIX_HINTS_HE, f"{code} missing Hebrew fix hint"
