# HTML Report Template

Reference loaded on demand by `qa-html-reporter` agent. Self-contained — no CDN.

## Full HTML structure

```html
<!DOCTYPE html>
<html lang="{LANG}" {RTL_DIR}>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Test Coverage — {PROJECT_NAME}</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="header">
    <div class="header-inner">
      <h1>{T_PROJECT}: {PROJECT_NAME}</h1>
      <div class="run-meta">
        <span>{T_RUN_TYPE}: {RUN_TYPE}</span>
        <span>{T_GENERATED}: {GENERATED_AT}</span>
      </div>
    </div>
  </header>

  <main class="container">
    <section class="scorecard">
      <div class="score-circle {SCORE_CLASS}">
        <div class="score-num">{QUALITY_SCORE}</div>
        <div class="score-label">{T_QUALITY_SCORE}</div>
      </div>
      <div class="summary-stats">
        <div><span>{T_NEW}</span><strong>{TESTS_NEW}</strong></div>
        <div><span>{T_UPDATED}</span><strong>{TESTS_UPDATED}</strong></div>
        <div><span>{T_FLAKY}</span><strong>{FLAKY_COUNT}</strong></div>
      </div>
    </section>

    <section class="card">
      <h2>{T_COVERAGE}</h2>
      <div class="bars">
        {COVERAGE_BARS}
      </div>
    </section>

    <section class="card">
      <h2>{T_TIMELINE}</h2>
      <table class="timeline-table">
        <thead><tr><th>{T_STEP}</th><th>{T_DURATION}</th><th>{T_STATUS}</th></tr></thead>
        <tbody>{TIMELINE_ROWS}</tbody>
      </table>
    </section>

    <section class="card">
      <h2>{T_MODULES}</h2>
      <table class="modules-table">
        <thead><tr><th>{T_PATH}</th><th>{T_TYPE}</th><th>{T_STATUS}</th><th>{T_TESTS}</th></tr></thead>
        <tbody>{MODULE_ROWS}</tbody>
      </table>
    </section>

    {UI_ARTIFACTS_SECTION}
    {A11Y_ARTIFACTS_SECTION}
    {GAPS_SECTION}
    {VULNS_SECTION}
    {FLAKY_SECTION}
    {INSTALLS_SECTION}
  </main>

  <footer><small>QA-Skills · {GENERATED_AT}</small></footer>
</body>
</html>
```

## Full CSS

```css
:root {
  --red: #E53E3E; --orange: #DD6B20; --green: #38A169; --gray: #718096;
  --bg: #F7FAFC; --surface: #FFFFFF; --border: #E2E8F0;
  --text-primary: #2D3748; --text-secondary: #718096;
  --badge-covered: #C6F6D5; --badge-partial: #FEFCBF;
  --badge-uncovered: #FED7D7; --badge-unchanged: #EDF2F7;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1A202C; --surface: #2D3748; --border: #4A5568;
    --text-primary: #E2E8F0; --text-secondary: #A0AEC0;
    --badge-covered: #22543D; --badge-partial: #744210;
    --badge-uncovered: #742A2A; --badge-unchanged: #2D3748;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text-primary);
  line-height: 1.5;
}
.header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 1.5rem 2rem;
}
.header-inner { max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 1.5rem; }
.run-meta span { margin-left: 1rem; color: var(--text-secondary); font-size: 0.9rem; }
.container { max-width: 1200px; margin: 2rem auto; padding: 0 2rem; }
.scorecard {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 2rem;
  display: flex;
  align-items: center;
  gap: 3rem;
  margin-bottom: 2rem;
}
.score-circle {
  width: 120px; height: 120px;
  border-radius: 50%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 4px solid var(--green);
}
.score-circle.medium { border-color: var(--orange); }
.score-circle.low { border-color: var(--red); }
.score-num { font-size: 2.5rem; font-weight: bold; }
.score-label { font-size: 0.8rem; color: var(--text-secondary); }
.summary-stats { display: flex; gap: 2rem; }
.summary-stats div { display: flex; flex-direction: column; }
.summary-stats span { color: var(--text-secondary); font-size: 0.85rem; }
.summary-stats strong { font-size: 1.5rem; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}
.card h2 { margin-bottom: 1rem; font-size: 1.2rem; }
.bars { display: flex; flex-direction: column; gap: 0.75rem; }
.bar { display: flex; align-items: center; gap: 1rem; }
.bar-label { width: 100px; font-size: 0.9rem; color: var(--text-secondary); }
.bar-track {
  flex: 1; height: 8px; background: var(--badge-unchanged); border-radius: 4px; overflow: hidden;
}
.bar-fill { height: 100%; background: var(--green); transition: width 0.3s; }
.bar-pct { width: 60px; text-align: right; font-size: 0.9rem; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 0.6rem; border-bottom: 1px solid var(--border); text-align: left; }
th { font-weight: 600; color: var(--text-secondary); font-size: 0.85rem; }
.badge {
  display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px;
  font-size: 0.75rem; font-weight: 600;
}
.badge.covered { background: var(--badge-covered); color: var(--green); }
.badge.partial { background: var(--badge-partial); color: var(--orange); }
.badge.uncovered { background: var(--badge-uncovered); color: var(--red); }
.badge.unchanged { background: var(--badge-unchanged); color: var(--text-secondary); }
.severity-high { color: var(--red); }
.severity-medium { color: var(--orange); }
.severity-low { color: var(--gray); }
footer { text-align: center; padding: 2rem; color: var(--text-secondary); font-size: 0.85rem; }
[dir="rtl"] .summary-stats { flex-direction: row-reverse; }
[dir="rtl"] th, [dir="rtl"] td { text-align: right; }
.artifact-link {
  display: inline-block; padding: 0.5rem 1rem; margin: 0.25rem 0.5rem 0.25rem 0;
  background: var(--badge-covered); color: var(--green);
  border-radius: 4px; text-decoration: none; font-size: 0.9rem; font-weight: 600;
}
.artifact-link:hover { opacity: 0.85; }
.thumb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; margin-top: 1rem; }
.thumb-grid a { display: block; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; background: var(--bg); }
.thumb-grid img { width: 100%; height: 140px; object-fit: cover; display: block; }
.thumb-caption { padding: 0.4rem; font-size: 0.75rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.media-list { list-style: none; padding: 0; margin: 0.5rem 0; }
.media-list li { padding: 0.4rem 0; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
.media-list a { color: var(--text-primary); text-decoration: none; }
.media-list a:hover { text-decoration: underline; }
.installs-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.installs-list li { background: var(--badge-unchanged); padding: 0.3rem 0.6rem; border-radius: 4px; list-style: none; font-size: 0.85rem; }
details { margin-top: 1rem; }
details summary { cursor: pointer; color: var(--text-secondary); font-size: 0.9rem; }
```

## Locale strings

```json
{
  "en": {
    "T_PROJECT": "Project",
    "T_RUN_TYPE": "Run type",
    "T_GENERATED": "Generated",
    "T_QUALITY_SCORE": "Quality score",
    "T_NEW": "New tests",
    "T_UPDATED": "Updated",
    "T_FLAKY": "Flaky",
    "T_COVERAGE": "Coverage",
    "T_TIMELINE": "Timeline",
    "T_STEP": "Step",
    "T_DURATION": "Duration",
    "T_STATUS": "Status",
    "T_MODULES": "Modules",
    "T_PATH": "Path",
    "T_TYPE": "Type",
    "T_TESTS": "Tests",
    "T_GAPS": "Gaps",
    "T_VULNS": "Vulnerabilities",
    "T_FLAKY_TESTS": "Flaky tests",
    "T_UI_ARTIFACTS": "UI test artifacts",
    "T_OPEN_PLAYWRIGHT": "Open Playwright report ↗",
    "T_SCREENSHOTS": "Failure screenshots",
    "T_VIDEOS": "Videos",
    "T_TRACES": "Traces (open in trace viewer)",
    "T_NO_FAILURES": "No failure artifacts captured ✅",
    "T_A11Y_ARTIFACTS": "Accessibility report",
    "T_OPEN_AXE": "Open axe-core report ↗",
    "T_INSTALLS": "Auto-installed dependencies"
  },
  "he": {
    "T_PROJECT": "פרויקט",
    "T_RUN_TYPE": "סוג ריצה",
    "T_GENERATED": "נוצר",
    "T_QUALITY_SCORE": "ציון איכות",
    "T_NEW": "בדיקות חדשות",
    "T_UPDATED": "עודכנו",
    "T_FLAKY": "לא יציבות",
    "T_COVERAGE": "כיסוי",
    "T_TIMELINE": "ציר זמן",
    "T_STEP": "שלב",
    "T_DURATION": "משך",
    "T_STATUS": "סטטוס",
    "T_MODULES": "מודולים",
    "T_PATH": "נתיב",
    "T_TYPE": "סוג",
    "T_TESTS": "בדיקות",
    "T_GAPS": "פערים",
    "T_VULNS": "פגיעויות",
    "T_FLAKY_TESTS": "בדיקות לא יציבות",
    "T_UI_ARTIFACTS": "ארטיפקטים מבדיקות UI",
    "T_OPEN_PLAYWRIGHT": "פתח דוח Playwright ↗",
    "T_SCREENSHOTS": "צילומי מסך מכשלים",
    "T_VIDEOS": "וידאו",
    "T_TRACES": "Traces (לפתיחה ב-trace viewer)",
    "T_NO_FAILURES": "לא נלכדו ארטיפקטים מכשלים ✅",
    "T_A11Y_ARTIFACTS": "דוח נגישות",
    "T_OPEN_AXE": "פתח דוח axe-core ↗",
    "T_INSTALLS": "תלויות שהותקנו אוטומטית"
  }
}
```

## Score class mapping

```python
def score_class(score: int) -> str:
    if score >= 80: return ""        # green (default)
    if score >= 50: return "medium"  # orange
    return "low"                     # red
```

## UI artifacts section template

Render only when `report_data.ui_artifacts.playwright_report` is non-null. All paths are converted to relative form via `to_relative()` (see qa-html-reporter.md "Path resolution for artifact links").

```python
def render_ui_artifacts(ua, t, project_root):
    if not ua or not ua.get("playwright_report"):
        return ""
    pr = to_relative(ua["playwright_report"], project_root)
    shots = ua.get("screenshots", [])
    vids  = ua.get("videos", [])
    trcs  = ua.get("traces", [])

    parts = [f'<section class="card"><h2>{t["T_UI_ARTIFACTS"]}</h2>']
    parts.append(f'<a class="artifact-link" href="{pr}" target="_blank" rel="noopener">{t["T_OPEN_PLAYWRIGHT"]}</a>')

    if shots:
        head = shots[:8]; rest = shots[8:24]
        parts.append(f'<h3 style="margin-top:1.25rem;font-size:1rem;">{t["T_SCREENSHOTS"]} ({len(shots)})</h3>')
        parts.append('<div class="thumb-grid">')
        for s in head:
            rel = to_relative(s, project_root)
            name = s.split("/")[-1]
            parts.append(f'<a href="{rel}" target="_blank" rel="noopener"><img src="{rel}" loading="lazy" alt="{name}"><div class="thumb-caption">{name}</div></a>')
        parts.append('</div>')
        if rest:
            parts.append(f'<details><summary>+{len(rest)} more</summary><div class="thumb-grid">')
            for s in rest:
                rel = to_relative(s, project_root)
                name = s.split("/")[-1]
                parts.append(f'<a href="{rel}" target="_blank" rel="noopener"><img src="{rel}" loading="lazy" alt="{name}"><div class="thumb-caption">{name}</div></a>')
            parts.append('</div></details>')
    elif not vids and not trcs:
        parts.append(f'<p style="margin-top:1rem;color:var(--text-secondary);">{t["T_NO_FAILURES"]}</p>')

    if vids:
        parts.append(f'<h3 style="margin-top:1.25rem;font-size:1rem;">{t["T_VIDEOS"]} ({len(vids)})</h3><ul class="media-list">')
        for v in vids[:20]:
            rel = to_relative(v, project_root); name = v.split("/")[-1]
            parts.append(f'<li><a href="{rel}" target="_blank" rel="noopener">🎬 {name}</a></li>')
        parts.append('</ul>')
    if trcs:
        parts.append(f'<h3 style="margin-top:1.25rem;font-size:1rem;">{t["T_TRACES"]} ({len(trcs)})</h3><ul class="media-list">')
        for tr in trcs[:20]:
            rel = to_relative(tr, project_root); name = tr.split("/")[-1]
            parts.append(f'<li><a href="{rel}" download>📦 {name}</a></li>')
        parts.append('</ul>')
    parts.append('</section>')
    return "".join(parts)
```

## A11y artifacts section template

```python
def render_a11y_artifacts(aa, t, project_root):
    if not aa or not aa.get("axe_report"):
        return ""
    rel = to_relative(aa["axe_report"], project_root)
    return (
        f'<section class="card"><h2>{t["T_A11Y_ARTIFACTS"]}</h2>'
        f'<a class="artifact-link" href="{rel}" target="_blank" rel="noopener">{t["T_OPEN_AXE"]}</a>'
        f'</section>'
    )
```

## Auto-installed dependencies section template

```python
def render_installs(installs, t):
    if not installs:
        return ""
    items = "".join(f'<li>📦 {i["name"]}{" (failed)" if i.get("exit", 0) != 0 else ""}</li>' for i in installs)
    return (
        f'<section class="card"><h2>{t["T_INSTALLS"]}</h2>'
        f'<ul class="installs-list">{items}</ul>'
        f'</section>'
    )
```
