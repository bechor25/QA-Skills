# Accessibility Test Patterns (WCAG 2.1 AA)

Reference loaded on demand by `qa-a11y-test` agent. Read only the section for the detected language.

**Sections by language:**
- TS/JS — `@axe-core/playwright`. See "TS/JS Templates" below.
- Python — `axe-playwright-python`. See "Python Templates" further down.

`path_contract.expected_files` (from orchestrator) is the immutable list. Sub-agent writes EXACTLY those paths.

---

# TS/JS Templates

## axe-core full-page scan

```typescript
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility — Home', () => {
  test('no critical or serious WCAG violations', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const critical = results.violations.filter(
      v => v.impact === 'critical' || v.impact === 'serious'
    );

    if (critical.length > 0) {
      const summary = critical.map(v =>
        `[${v.impact}] ${v.id}: ${v.description}\n  Affected: ${
          v.nodes.map(n => n.target.join(', ')).join('\n  ')
        }`
      ).join('\n\n');
      console.log('Critical/serious violations:\n' + summary);
    }

    expect(critical).toEqual([]);
  });
});
```

## Focus order

```typescript
test('keyboard tab moves focus through interactive elements', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const interactiveCount = await page.locator(
    'a[href], button, input:not([type="hidden"]), select, textarea, [tabindex]:not([tabindex="-1"])'
  ).count();

  for (let i = 0; i < Math.min(interactiveCount, 20); i++) {
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toBeFocused();
  }
});
```

## Heading hierarchy

```typescript
test('one h1 per page, no skipped levels', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const h1Count = await page.locator('h1').count();
  expect(h1Count).toBe(1);

  const headingLevels: number[] = [];
  for (const h of await page.locator('h1, h2, h3, h4, h5, h6').all()) {
    const tag = await h.evaluate(el => el.tagName);
    headingLevels.push(parseInt(tag.slice(1)));
  }

  for (let i = 1; i < headingLevels.length; i++) {
    expect(headingLevels[i] - headingLevels[i - 1]).toBeLessThanOrEqual(1);
  }
});
```

## ARIA names on interactive elements

```typescript
test('all buttons have accessible name', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  for (const btn of await page.locator('button').all()) {
    const text = (await btn.innerText()).trim();
    const aria = await btn.getAttribute('aria-label');
    const title = await btn.getAttribute('title');
    expect(text || aria || title, 'button missing accessible name').toBeTruthy();
  }
});

test('all images have alt text', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  for (const img of await page.locator('img').all()) {
    const alt = await img.getAttribute('alt');
    expect(alt, `image missing alt: ${await img.getAttribute('src')}`).not.toBeNull();
  }
});

test('all inputs have labels', async ({ page }) => {
  await page.goto('/');
  for (const input of await page.locator('input:not([type="hidden"])').all()) {
    const id = await input.getAttribute('id');
    const aria = await input.getAttribute('aria-label');
    const ariaBy = await input.getAttribute('aria-labelledby');
    const labelCount = id ? await page.locator(`label[for="${id}"]`).count() : 0;
    expect(labelCount > 0 || aria || ariaBy, 'input missing label').toBeTruthy();
  }
});
```

## RTL rendering (Hebrew/Arabic)

```typescript
test('RTL renders correctly', async ({ page }) => {
  await page.goto('/');
  const dir = await page.getAttribute('html', 'dir');
  const lang = await page.getAttribute('html', 'lang');
  if (lang?.startsWith('he') || lang?.startsWith('ar') || dir === 'rtl') {
    const computed = await page.evaluate(() =>
      window.getComputedStyle(document.body).direction
    );
    expect(computed).toBe('rtl');
  }
});
```

## Color contrast (subset of axe scan)

```typescript
test('no color contrast violations', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const results = await new AxeBuilder({ page })
    .withRules(['color-contrast'])
    .analyze();
  expect(results.violations).toEqual([]);
});
```

---

# Python Templates (axe-playwright-python)

## tests/a11y/conftest.py

```python
import pytest

@pytest.fixture(scope="session")
def base_url():
    import os
    return os.environ.get("BASE_URL", "http://localhost:8000")
```

## Pytest CLI invocation

```bash
cd "${PROJECT_ROOT}" && \
  python3 -m pytest tests/a11y/ \
    --screenshot=on \
    --output=tests/a11y/test-results \
    --html=tests/a11y/axe-report/index.html \
    --self-contained-html \
    --json-report --json-report-file=.qa-skills/pytest-a11y.json \
    -v
```

`--html=tests/a11y/axe-report/index.html` is what coverage-reporter sets as `axe_report` in report-data.json. Mandatory for Phase 9d.2.

## axe full-page scan — `tests/a11y/<page>/test_<page>.py`

```python
from playwright.sync_api import Page, expect
from axe_playwright_python.sync_playwright import Axe

def test_home_page_no_critical_violations(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.wait_for_load_state("networkidle")
    axe = Axe()
    results = axe.run(page, options={"runOnly": ["wcag2a","wcag2aa"]})
    critical = [v for v in results.response["violations"]
                if v["impact"] in ("critical","serious")]
    if critical:
        for v in critical:
            print(f"[{v['impact']}] {v['id']}: {v['description']}")
            for n in v["nodes"]:
                print(f"  affected: {n['target']}")
    assert critical == [], f"{len(critical)} critical/serious WCAG violations"
```

## Focus order

```python
def test_keyboard_tab_moves_focus(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.wait_for_load_state("networkidle")
    interactive = page.locator(
        'a[href], button, input:not([type="hidden"]), select, textarea, '
        '[tabindex]:not([tabindex="-1"])'
    )
    count = min(interactive.count(), 20)
    for _ in range(count):
        page.keyboard.press("Tab")
        focused = page.evaluate("() => document.activeElement?.tagName")
        assert focused, "no element focused after Tab"
```

## Heading hierarchy

```python
def test_one_h1_no_skipped_levels(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1").count() == 1, "expected exactly one h1"
    levels = []
    for h in page.locator("h1, h2, h3, h4, h5, h6").all():
        tag = h.evaluate("el => el.tagName")
        levels.append(int(tag[1]))
    for i in range(1, len(levels)):
        assert levels[i] - levels[i-1] <= 1, f"skipped heading level at index {i}: {levels}"
```

## ARIA names

```python
def test_all_buttons_have_accessible_name(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.wait_for_load_state("networkidle")
    for btn in page.locator("button").all():
        text  = btn.inner_text().strip()
        aria  = btn.get_attribute("aria-label")
        title = btn.get_attribute("title")
        assert text or aria or title, "button missing accessible name"

def test_all_images_have_alt(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.wait_for_load_state("networkidle")
    for img in page.locator("img").all():
        alt = img.get_attribute("alt")
        src = img.get_attribute("src")
        assert alt is not None, f"image missing alt: {src}"

def test_all_inputs_have_labels(page: Page, base_url: str):
    page.goto(base_url + "/")
    for inp in page.locator('input:not([type="hidden"])').all():
        id_   = inp.get_attribute("id")
        aria  = inp.get_attribute("aria-label")
        ariaby= inp.get_attribute("aria-labelledby")
        label_count = page.locator(f'label[for="{id_}"]').count() if id_ else 0
        assert label_count > 0 or aria or ariaby, f"input {id_} missing label"
```

## RTL rendering (Hebrew/Arabic)

```python
def test_rtl_renders_correctly(page: Page, base_url: str):
    page.goto(base_url + "/")
    dir_  = page.get_attribute("html", "dir")
    lang  = page.get_attribute("html", "lang") or ""
    if lang.startswith("he") or lang.startswith("ar") or dir_ == "rtl":
        computed = page.evaluate("() => window.getComputedStyle(document.body).direction")
        assert computed == "rtl"
```

## Color contrast (subset of axe scan)

```python
def test_no_color_contrast_violations(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.wait_for_load_state("networkidle")
    axe = Axe()
    results = axe.run(page, options={"runOnly": {"type": "rule", "values": ["color-contrast"]}})
    assert results.response["violations"] == []
```
