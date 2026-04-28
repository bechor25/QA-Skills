---
name: html-reporter
description: >
  Internal shared skill — generates a self-contained HTML report from report-data.json and
  opens it in the browser. Always called automatically by coverage-reporter at the end of every run.
  No server required — fully self-contained HTML file.

  Standalone use: "show me the coverage report", "open test report", "regenerate the HTML report",
  "reopen the report". Hebrew: "פתח את דוח הבדיקות", "הצג את הדוח", "צור את ה-HTML report".
---

# html-reporter

Generates a single self-contained HTML file from `report-data.json`.
Opens it in the browser. No server, no CDN, no external dependencies.

## Inputs

```json
{
  "project_root": "string",
  "report_data": { /* full report-data.json object */ }
}
```

## Output

```
{project_root}/test-reports/report-{PROJECT_NAME}-{YYYYMMDD-HHMM}.html
```

`PROJECT_NAME` = `os.path.basename(project_root)`, lowercased, spaces replaced with `-`.
`YYYYMMDD-HHMM` = UTC timestamp of generation.

## Self-contained requirements

**Absolutely no external references:**
- No `<link rel="stylesheet" href="...">` pointing to CDN
- No `<script src="...">` pointing to CDN
- No Google Fonts — use `system-ui, -apple-system, sans-serif`
- No images from URLs — SVG inline only
- All CSS in `<style>`, all JS in `<script>`

## Design tokens

```css
:root {
  --red:    #E53E3E;
  --orange: #DD6B20;
  --green:  #38A169;
  --gray:   #718096;
  --bg:     #F7FAFC;
  --surface: #FFFFFF;
  --border: #E2E8F0;
  --text-primary:   #2D3748;
  --text-secondary: #718096;
  --badge-covered:  #C6F6D5;
  --badge-partial:  #FEFCBF;
  --badge-uncovered:#FED7D7;
  --badge-unchanged:#EDF2F7;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:      #1A202C;
    --surface: #2D3748;
    --border:  #4A5568;
    --text-primary:   #E2E8F0;
    --text-secondary: #A0AEC0;
    --badge-covered:  #22543D;
    --badge-partial:  #744210;
    --badge-uncovered:#742A2A;
    --badge-unchanged:#2D3748;
  }
}
```

## Full HTML structure

Generate this document:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Test Coverage — {PROJECT_NAME}</title>
  <style>
    /* PASTE ALL CSS HERE — see sections below */
  </style>
</head>
<body>
  <!-- 1. Header bar -->
  <!-- 2. Coverage scorecard -->
  <!-- 3. Timeline -->
  <!-- 4. Module table -->
  <!-- 5. Gaps -->
  <!-- 6. Blind spots -->
  <!-- 7. Recommendations -->
  <!-- 8. Footer -->
  <script>
    /* PASTE ALL JS HERE — see sections below */
  </script>
</body>
</html>
```

---

## Section 1 — Header bar

```html
<header class="header">
  <div class="header-left">
    <h1>{PROJECT_NAME}</h1>
    <span class="run-badge">{run_type == "full" ? "Full scan" : "Incremental — N files changed"}</span>
  </div>
  <div class="header-right">
    <time datetime="{generated_at}">{formatted_date}</time>
    <a class="btn-outline" href="file://{project_root}/tests">Open tests folder</a>
  </div>
</header>
```

CSS:
```css
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 10;
}
.header h1 { font-size: 1.25rem; font-weight: 700; color: var(--text-primary); margin: 0; }
.run-badge {
  display: inline-block;
  margin-left: 0.75rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  background: #EBF8FF;
  color: #2B6CB0;
  font-size: 0.75rem;
  font-weight: 600;
}
.btn-outline {
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  text-decoration: none;
}
.btn-outline:hover { background: var(--bg); }
```

---

## Section 2 — Coverage scorecard (4 gauges)

Generate one SVG gauge per category. Formula: `COVERED_ARC = (pct / 100) * 314`.

```html
<section class="scorecard">
  <div class="gauge-grid">
    <!-- Repeat for each category: unit, ui, api, security -->
    <div class="gauge-card">
      <svg viewBox="0 0 120 120" width="120" height="120">
        <circle cx="60" cy="60" r="50" fill="none" stroke="var(--border)" stroke-width="12"/>
        <circle cx="60" cy="60" r="50" fill="none"
          stroke="{COLOR_FOR_PCT}"
          stroke-width="12"
          stroke-dasharray="{COVERED_ARC} 314"
          stroke-dashoffset="78.5"
          stroke-linecap="round"
          transform="rotate(-90 60 60)"/>
        <text x="60" y="55" text-anchor="middle" font-size="22" font-weight="700"
              fill="var(--text-primary)">{PCT}%</text>
        <text x="60" y="74" text-anchor="middle" font-size="11"
              fill="var(--text-secondary)">{LABEL}</text>
      </svg>
      <p class="gauge-sub">{covered}/{total} files</p>
    </div>
  </div>

  <div class="summary-pills">
    <span class="pill">📁 {files_scanned} files scanned</span>
    <span class="pill">✅ {new_tests_generated} tests generated</span>
    <span class="pill">🔄 {tests_updated} updated</span>
    <span class="pill">⏸ {tests_unchanged} unchanged</span>
  </div>
</section>
```

Color for pct: `pct >= 80 → var(--green)`, `pct >= 50 → var(--orange)`, `else → var(--red)`.

CSS:
```css
.scorecard { padding: 2rem; background: var(--bg); }
.gauge-grid {
  display: flex;
  gap: 2rem;
  justify-content: center;
  flex-wrap: wrap;
  margin-bottom: 1.5rem;
}
.gauge-card { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; }
.gauge-sub { font-size: 0.8rem; color: var(--text-secondary); margin: 0; }
.summary-pills { display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }
.pill {
  padding: 0.35rem 0.75rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}
```

---

## Section 3 — Timeline

```html
<section class="timeline-section">
  <h2>What was done</h2>
  <table class="timeline-table">
    <thead>
      <tr><th>Step</th><th>Result</th><th>Duration</th></tr>
    </thead>
    <tbody>
      <!-- For each timeline entry: -->
      <tr>
        <td class="step-name">{step}</td>
        <td>
          <span class="status-icon {status}">{status == "done" ? "✓" : status == "skipped" ? "⟳" : "✗"}</span>
          {status_label}
        </td>
        <td class="duration">{duration_ms > 0 ? duration_ms + "ms" : "—"}</td>
      </tr>
    </tbody>
  </table>
</section>
```

CSS:
```css
.timeline-section { padding: 1.5rem 2rem; }
.timeline-section h2 { font-size: 1rem; font-weight: 700; margin-bottom: 1rem; }
.timeline-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.timeline-table th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 2px solid var(--border);
  color: var(--text-secondary);
  font-weight: 600;
}
.timeline-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
.status-icon.done    { color: var(--green); }
.status-icon.skipped { color: var(--gray); }
.status-icon.failed  { color: var(--red); }
.duration { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
```

---

## Section 4 — Module table (filterable)

```html
<section class="modules-section">
  <div class="modules-header">
    <h2>Modules</h2>
    <div class="filters">
      <button class="filter-btn active" onclick="filterModules('all')">All</button>
      <button class="filter-btn" onclick="filterModules('uncovered')">Uncovered</button>
      <button class="filter-btn" onclick="filterModules('partial')">Partial</button>
      <button class="filter-btn" onclick="filterModules('blind-spots')">Has Blind Spots</button>
      <input class="search-box" type="search" placeholder="Search modules..." 
             oninput="searchModules(this.value)">
    </div>
  </div>

  <table class="module-table" id="module-table">
    <thead>
      <tr>
        <th>Module</th><th>Language</th><th>Status</th>
        <th>Tests</th><th>Gaps</th><th>Blind Spots</th>
      </tr>
    </thead>
    <tbody>
      <!-- For each module: -->
      <tr data-status="{status}" data-has-blindspots="{blind_spots.length > 0}">
        <td class="module-path">{path}</td>
        <td><span class="lang-badge">{language}</span></td>
        <td><span class="status-badge {status}">{status}</span></td>
        <td>
          {tests_generated.length > 0 
            ? tests_generated.map(t => `<a class="test-link" href="file://${t}">${basename(t)}</a>`).join(', ')
            : '<span class="none">—</span>'}
        </td>
        <td>
          {gaps.length > 0
            ? `<details><summary>${gaps.length} gap(s)</summary><ul>${gaps.map(g => `<li>${g}</li>`).join('')}</ul></details>`
            : '—'}
        </td>
        <td>
          {blind_spots.length > 0
            ? `<details><summary>${blind_spots.length} spot(s)</summary><ul>${blind_spots.map(b => `<li>${b}</li>`).join('')}</ul></details>`
            : '—'}
        </td>
      </tr>
    </tbody>
  </table>
</section>
```

CSS:
```css
.modules-section { padding: 1.5rem 2rem; }
.modules-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem; }
.filters { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.filter-btn {
  padding: 0.3rem 0.75rem; border: 1px solid var(--border);
  border-radius: 6px; font-size: 0.8rem; background: var(--surface);
  color: var(--text-secondary); cursor: pointer;
}
.filter-btn.active { background: var(--text-primary); color: #fff; border-color: var(--text-primary); }
.search-box {
  padding: 0.3rem 0.6rem; border: 1px solid var(--border); border-radius: 6px;
  font-size: 0.8rem; background: var(--surface); color: var(--text-primary);
}
.module-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.module-table th { text-align: left; padding: 0.5rem; border-bottom: 2px solid var(--border); color: var(--text-secondary); }
.module-table td { padding: 0.5rem; border-bottom: 1px solid var(--border); vertical-align: top; }
.module-path { font-family: monospace; font-size: 0.75rem; }
.status-badge {
  padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.72rem; font-weight: 600;
}
.status-badge.covered   { background: var(--badge-covered);   color: #22543D; }
.status-badge.partial   { background: var(--badge-partial);   color: #744210; }
.status-badge.uncovered { background: var(--badge-uncovered); color: #742A2A; }
.status-badge.unchanged { background: var(--badge-unchanged); color: var(--gray); }
.status-badge.error     { background: var(--badge-uncovered); color: #742A2A; }
.test-link { color: #3182CE; text-decoration: none; font-family: monospace; font-size: 0.72rem; }
.test-link:hover { text-decoration: underline; }
details > summary { cursor: pointer; color: var(--text-secondary); }
details ul { margin: 0.25rem 0 0 1rem; padding: 0; font-size: 0.75rem; }
details li { margin-bottom: 0.2rem; }
```

---

## Section 5 — Gaps

```html
<section class="gaps-section">
  <h2>Coverage Gaps</h2>
  
  <div class="gap-group">
    <h3>🔴 High Priority</h3>
    {high_gaps.map(g => `
      <div class="gap-card high">
        <span class="gap-module">{g.module}</span>
        <p>{g.reason}</p>
      </div>
    `)}
  </div>
  
  <div class="gap-group">
    <h3>🟡 Medium Priority</h3>
    {/* same pattern */}
  </div>
  
  <div class="gap-group">
    <h3>🟢 Low Priority</h3>
    {/* same pattern */}
  </div>
</section>
```

CSS:
```css
.gaps-section { padding: 1.5rem 2rem; }
.gap-group { margin-bottom: 1.5rem; }
.gap-group h3 { font-size: 0.9rem; font-weight: 700; margin-bottom: 0.75rem; }
.gap-card {
  padding: 0.75rem 1rem; border-left: 4px solid; border-radius: 0 6px 6px 0;
  margin-bottom: 0.5rem; background: var(--surface);
}
.gap-card.high   { border-color: var(--red);    }
.gap-card.medium { border-color: var(--orange); }
.gap-card.low    { border-color: var(--green);  }
.gap-module { font-family: monospace; font-size: 0.75rem; color: var(--text-secondary); display: block; margin-bottom: 0.25rem; }
.gap-card p { margin: 0; font-size: 0.85rem; color: var(--text-primary); }
```

---

## Section 6 — Blind Spots

```html
<section class="blindspots-section">
  <h2>Blind Spots <span class="section-sub">What humans typically miss</span></h2>
  
  <div class="blindspot-grid">
    {blind_spots.map(bs => `
      <div class="blindspot-card">
        <div class="blindspot-header">
          <span class="blindspot-category {bs.category}">{bs.category.toUpperCase()}</span>
          <span class="blindspot-module">{bs.module}</span>
        </div>
        <p class="blindspot-desc">{bs.description}</p>
      </div>
    `)}
  </div>
</section>
```

CSS:
```css
.blindspots-section { padding: 1.5rem 2rem; background: var(--bg); }
.section-sub { font-size: 0.8rem; font-weight: 400; color: var(--text-secondary); margin-left: 0.5rem; }
.blindspot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; margin-top: 1rem; }
.blindspot-card {
  padding: 1rem; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px;
}
.blindspot-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
.blindspot-category {
  padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.65rem; font-weight: 700;
  text-transform: uppercase;
}
.blindspot-category.unit     { background: #EBF8FF; color: #2B6CB0; }
.blindspot-category.ui       { background: #FAF5FF; color: #553C9A; }
.blindspot-category.api      { background: #FFFAF0; color: #7B341E; }
.blindspot-category.security { background: #FFF5F5; color: #742A2A; }
.blindspot-module { font-family: monospace; font-size: 0.7rem; color: var(--text-secondary); }
.blindspot-desc { font-size: 0.82rem; color: var(--text-primary); margin: 0; line-height: 1.5; }
```

---

## Section 7 — Recommendations

```html
<section class="recommendations-section">
  <h2>Recommendations</h2>
  <ol class="recommendations-list">
    {recommendations.map(r => `
      <li>
        <span class="rec-module">{r.module}</span>
        {r.text}
      </li>
    `)}
  </ol>
</section>
```

---

## Section 8 — Footer

```html
<footer class="footer">
  <div class="footer-links">
    <a href="file://{project_root}/test-state.json">test-state.json</a>
    <a href="file://{project_root}/test-reports/report-data.json">report-data.json</a>
  </div>
  <p class="footer-hint">Run again when: you add new files or change existing logic.</p>
  <p class="footer-meta">Generated by qa-skills test-orchestrator • {generated_at}</p>
</footer>
```

---

## JavaScript — filtering and search

```javascript
function filterModules(filter) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  
  document.querySelectorAll('#module-table tbody tr').forEach(row => {
    if (filter === 'all') {
      row.style.display = '';
    } else if (filter === 'blind-spots') {
      row.style.display = row.dataset.hasBlindspots === 'true' ? '' : 'none';
    } else {
      row.style.display = row.dataset.status === filter ? '' : 'none';
    }
  });
}

function searchModules(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('#module-table tbody tr').forEach(row => {
    const path = row.querySelector('.module-path')?.textContent?.toLowerCase() || '';
    row.style.display = path.includes(q) ? '' : 'none';
  });
}

// Persist filter on sort — re-apply after any DOM change
document.addEventListener('DOMContentLoaded', () => {
  // Auto-collapse all details elements on load (expand on click)
  document.querySelectorAll('details').forEach(d => d.removeAttribute('open'));
});
```

---

## Open in browser

After writing the file:

```python
import webbrowser, os, sys

report_path = os.path.abspath(output_path)
file_url = f"file://{report_path}"

try:
    opened = webbrowser.open(file_url)
    if opened:
        print(f"\n✅ Report opened in browser: {report_path}")
    else:
        raise Exception("webbrowser.open returned False")
except Exception:
    # Headless environment fallback
    print(f"\n📄 Report saved: {report_path}")
    if sys.platform == "darwin":
        print(f"   Open: open \"{report_path}\"")
    elif sys.platform == "win32":
        print(f"   Open: start \"{report_path}\"")
    else:
        print(f"   Open: xdg-open \"{report_path}\"")
```

Then print the final summary:
```
✅ Done.
   New tests:   {new_tests_generated}
   Updated:     {tests_updated}
   Unchanged:   {tests_unchanged}
   Gaps found:  {len(gaps)} ({len([g for g in gaps if g.severity=="high"])} high)
   Blind spots: {len(blind_spots)}
   Report:      {report_path}
```
