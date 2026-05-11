"""compute_quality_score tests."""

from __future__ import annotations

from qa_skills.quality import compute_quality_score


def test_zero_coverage_zero_score():
    assert compute_quality_score({}) == 0


def test_full_coverage_no_bonuses():
    cov = {
        "unit":     {"pct": 100},
        "api":      {"pct": 100},
        "ui":       {"pct": 100},
        "security": {"pct": 100},
    }
    # 100*0.3*0.8 + 100*0.3*0.8 + 100*0.2*0.8 + 100*0.2*0.8 = 24+24+16+16 = 80
    assert compute_quality_score(cov) == 80


def test_full_coverage_with_contract_bonus():
    cov = {
        "unit":     {"pct": 100},
        "api":      {"pct": 100},
        "ui":       {"pct": 100},
        "security": {"pct": 100},
        "contract": {"pct": 100},
    }
    # 80 + 5 contract bonus
    assert compute_quality_score(cov) == 85


def test_full_coverage_with_a11y_bonus():
    cov = {
        "unit":     {"pct": 100},
        "api":      {"pct": 100},
        "ui":       {"pct": 100},
        "security": {"pct": 100},
        "a11y":     {"pct": 100, "critical_violations": 0},
    }
    # 80 + 3 a11y bonus
    assert compute_quality_score(cov) == 83


def test_flaky_penalty():
    cov = {"unit": {"pct": 100}, "api": {"pct": 100}, "ui": {"pct": 100}, "security": {"pct": 100}}
    # 80 - 2*5 flaky penalty = 70
    assert compute_quality_score(cov, flaky_tests=[{}, {}, {}, {}, {}]) == 70


def test_high_severity_gap_penalty():
    cov = {"unit": {"pct": 100}, "api": {"pct": 100}, "ui": {"pct": 100}, "security": {"pct": 100}}
    gaps = [{"severity": "high"}, {"severity": "low"}, {"severity": "high"}]
    # 80 - 2*5 = 70 (only high gaps count)
    assert compute_quality_score(cov, gaps=gaps) == 70


def test_score_clamped_to_100():
    cov = {
        "unit": {"pct": 100}, "api": {"pct": 100}, "ui": {"pct": 100}, "security": {"pct": 100},
        "contract": {"pct": 100},
        "a11y": {"pct": 100, "critical_violations": 0},
    }
    # 80 + 5 + 3 = 88. No way to exceed without bonus stacking.
    score = compute_quality_score(cov)
    assert 0 <= score <= 100
    assert score == 88


def test_score_clamped_to_0():
    cov = {"unit": {"pct": 0}}
    flaky = [{}] * 100
    gaps = [{"severity": "high"}] * 100
    score = compute_quality_score(cov, flaky_tests=flaky, gaps=gaps)
    assert score == 0
