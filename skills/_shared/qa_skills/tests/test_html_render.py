"""html_render tests."""

from __future__ import annotations

import re

from qa_skills.html_render import render_html, write_html_report


def _minimal_report(**overrides):
    base = {
        "version": "2.0", "run_id": "r1",
        "project_root": "/tmp/x", "language": "python",
        "locale": "en", "generated_at": "2026-05-10T12:00:00Z",
        "run_type": "full", "quality_score": 78,
        "summary": {"modules_total": 5, "tests_new": 30, "flaky_count": 0},
        "coverage_by_category": {
            "unit": {"status": "passed", "pct": 100, "total": 5,
                     "covered_items": ["a","b","c","d","e"], "missing_items": [], "files": []},
            "api": {"status": "partial", "pct": 50, "total": 4,
                    "covered_items": ["GET /a","POST /b"], "missing_items": ["GET /c","POST /d"], "files": []},
            "ui": {"status": "skipped:no_server", "pct": 0, "total": 0,
                   "covered_items": [], "missing_items": [], "files": []},
        },
        "modules": [], "vulnerabilities_found": [],
        "gaps": [{"severity": "high", "path": "app/payments.py", "reason": "uncovered payments"}],
        "flaky_tests": [],
        "timeline": [],
        "warnings": [],
        "ui_artifacts": {},
        "a11y_artifacts": {},
    }
    base.update(overrides)
    return base


def test_render_returns_valid_html_doctype():
    html = render_html(_minimal_report())
    assert html.startswith("<!doctype html>")
    assert "</html>" in html


def test_render_includes_quality_score():
    html = render_html(_minimal_report(quality_score=87))
    assert "87" in html
    assert "/100" in html


def test_render_score_colors_by_threshold():
    assert "score green" in render_html(_minimal_report(quality_score=90))
    assert "score orange" in render_html(_minimal_report(quality_score=60))
    assert "score red" in render_html(_minimal_report(quality_score=30))


def test_render_shows_missing_items_collapsible():
    html = render_html(_minimal_report())
    assert "<details>" in html
    assert "GET /c" in html


def test_render_shows_all_covered_when_missing_empty():
    html = render_html(_minimal_report())
    assert "All covered" in html


def test_render_skipped_category_renders_NA_when_total_zero():
    html = render_html(_minimal_report())
    assert "no signal" in html


def test_render_hebrew_locale_sets_rtl():
    html = render_html(_minimal_report(locale="he"))
    assert 'lang="he"' in html
    assert 'dir="rtl"' in html
    assert "ציון איכות" in html


def test_render_gaps_section_renders_high_severity():
    html = render_html(_minimal_report())
    assert "app/payments.py" in html
    assert "uncovered payments" in html


def test_write_html_report_to_file(tmp_path):
    out = tmp_path / "report.html"
    written = write_html_report(_minimal_report(), out)
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert content.startswith("<!doctype html>")
    assert len(content) > 1000   # substantial size


def test_render_no_external_resources():
    """Self-contained: no CDN, no external CSS/JS/font."""
    html = render_html(_minimal_report())
    assert 'href="http' not in html
    assert 'src="http' not in html
    assert "googleapis" not in html
    assert "cdnjs" not in html


# ---------- B3: stub + contract banners ----------


def test_no_banner_when_clean():
    html = render_html(_minimal_report())
    # .banner-warn lives in CSS always; the rendered <div class="banner-warn">
    # must not appear when there are no stubs/violations.
    assert 'class="banner-warn"' not in html


def test_stub_banner_renders_from_coverage_stub_files():
    rd = _minimal_report()
    rd["coverage_by_category"]["api"]["stub_files"] = [
        "tests/api/auth/test_login.py",
        "tests/api/users/test_users.py",
    ]
    html = render_html(rd)
    assert 'class="banner-warn"' in html
    assert "Stub tests detected" in html
    assert "tests/api/auth/test_login.py" in html
    assert "tests/api/users/test_users.py" in html


def test_stub_banner_renders_from_warnings():
    rd = _minimal_report(warnings=[
        "stub_content:ui:tests/ui/Home/Home.spec.ts",
        "stub_content:a11y:tests/a11y/Login/Login.a11y.spec.ts",
    ])
    html = render_html(rd)
    assert 'class="banner-warn"' in html
    assert "tests/ui/Home/Home.spec.ts" in html
    assert "tests/a11y/Login/Login.a11y.spec.ts" in html


def test_contract_violation_banner_renders():
    rd = _minimal_report(warnings=[
        "path_contract_violation:tests/api/auth/test_login.api.test.ts",
    ])
    html = render_html(rd)
    assert 'class="banner-warn"' in html
    assert "Path-contract violations" in html
    assert "tests/api/auth/test_login.api.test.ts" in html


def test_banners_in_hebrew_locale():
    rd = _minimal_report(locale="he", warnings=[
        "stub_content:ui:tests/ui/Home/Home.spec.ts",
    ])
    html = render_html(rd)
    assert "זוהו קבצי stub" in html


def test_stub_files_deduplicated_across_sources():
    """Same path in stub_files + warnings → listed once."""
    rd = _minimal_report(warnings=[
        "stub_content:api:tests/api/auth/test_login.py",
    ])
    rd["coverage_by_category"]["api"]["stub_files"] = [
        "tests/api/auth/test_login.py",
    ]
    html = render_html(rd)
    assert html.count("tests/api/auth/test_login.py") == 1
