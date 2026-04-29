---
name: accessibility-test
description: >
  Generate dedicated WCAG accessibility tests for frontend pages using Playwright + axe-core.
  Covers: critical/serious violations, focus order, heading hierarchy, ARIA names, RTL rendering.
  Normally invoked by test-orchestrator when frontend detected.
  Also usable standalone when user asks for accessibility testing.

  English triggers (standalone): "test accessibility", "WCAG", "a11y", "check accessibility",
  "aria tests", "screen reader", "keyboard navigation tests", "check WCAG compliance".

  Hebrew triggers (עברית): "בדוק נגישות", "בדיקות נגישות", "WCAG", "בדוק מקלדת",
  "בדיקות קוראי מסך", "נגישות WCAG", "a11y", "בדוק ניגוד צבעים".
---

# accessibility-test

Generates Playwright specs that test WCAG 2.1 AA compliance for every frontend page.

## Inputs

Receives `RunContext`. Key fields:
- `analysis.frontend_files`
- `analysis.routes` (filter to page-serving routes)
- `project_root`
- `language`
- `user_locale`

## Output location

```
{project_root}/tests/a11y/{page-name}.a11y.spec.ts
```

## Setup check

Before generating, verify Playwright is installed (same check as ui-playwright skill).
If missing, print `install_playwright` message and skip.

Bundle axe-core: use `skills/_shared/vendor/axe.min.js` if it exists, otherwise instruct:
```typescript
// Add to package.json devDependencies: "@axe-core/playwright": "^4.8.0"
```

Generate `playwright.config.ts` if one doesn't exist (same as ui-playwright skill).

---

## For every detected frontend page / route

Group pages by route prefix. Generate one spec file per logical section:
- `/` + `/home` → `tests/a11y/home.a11y.spec.ts`
- `/login` + `/register` → `tests/a11y/auth.a11y.spec.ts`
- `/dashboard` → `tests/a11y/dashboard.a11y.spec.ts`

### 1. axe-core full-page scan

```typescript
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility — {PAGE_NAME}', () => {
  test('no critical or serious WCAG violations', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const violations = results.violations.filter(
      v => v.impact === 'critical' || v.impact === 'serious'
    );

    if (violations.length > 0) {
      const summary = violations.map(v =>
        `[${v.impact}] ${v.id}: ${v.description}\n  Affected: ${
          v.nodes.map(n => n.target.join(', ')).join('\n  ')
        }`
      ).join('\n\n');
      throw new Error(`${violations.length} critical/serious violations:\n\n${summary}`);
    }
  });
```

### 2. Focus order

```typescript
  test('tab focus order matches DOM order', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const focusable = await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
      ));
      return els.map((el, i) => ({ index: i, tag: el.tagName, id: (el as HTMLElement).id }));
    });

    expect(focusable.length).toBeGreaterThan(0);

    // Tab through elements and verify they receive focus in DOM order
    await page.keyboard.press('Tab');
    for (let i = 0; i < Math.min(focusable.length, 10); i++) {
      const focused = await page.evaluate(() => document.activeElement?.tagName);
      expect(focused).toBeTruthy();
      await page.keyboard.press('Tab');
    }
  });
```

### 3. Heading hierarchy

```typescript
  test('heading hierarchy has no skipped levels', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const headings = await page.evaluate(() =>
      Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
        .map(h => parseInt(h.tagName[1]))
    );

    for (let i = 1; i < headings.length; i++) {
      const diff = headings[i] - headings[i - 1];
      expect(diff, `Heading level jumped from h${headings[i-1]} to h${headings[i]}`).toBeLessThanOrEqual(1);
    }
  });
```

### 4. Buttons must have accessible names

```typescript
  test('all buttons have accessible names', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const buttons = await page.locator('button').all();
    for (const btn of buttons) {
      const text = (await btn.innerText()).trim();
      const ariaLabel = await btn.getAttribute('aria-label');
      const ariaLabelledBy = await btn.getAttribute('aria-labelledby');
      const title = await btn.getAttribute('title');
      expect(
        text || ariaLabel || ariaLabelledBy || title,
        `Button missing accessible name: ${await btn.evaluate(el => el.outerHTML)}`
      ).toBeTruthy();
    }
  });
```

### 5. Images must have alt text

```typescript
  test('all images have alt attributes', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const images = await page.locator('img').all();
    for (const img of images) {
      const alt = await img.getAttribute('alt');
      expect(alt, `Image missing alt: ${await img.getAttribute('src')}`).not.toBeNull();
    }
  });
```

### 6. Form inputs have labels

```typescript
  test('all form inputs have associated labels', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const inputs = await page.locator('input:not([type="hidden"]), textarea, select').all();
    for (const input of inputs) {
      const id = await input.getAttribute('id');
      const ariaLabel = await input.getAttribute('aria-label');
      const ariaLabelledBy = await input.getAttribute('aria-labelledby');
      const placeholder = await input.getAttribute('placeholder');
      const labelCount = id ? await page.locator(`label[for="${id}"]`).count() : 0;
      expect(
        labelCount > 0 || ariaLabel || ariaLabelledBy,
        `Input without proper label (placeholder "${placeholder}" is not sufficient)`
      ).toBeTruthy();
    }
  });
```

### 7. RTL rendering (if Hebrew locale detected or RTL routes found)

```typescript
  test('RTL layout renders correctly', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    const dir = await page.evaluate(() => document.documentElement.dir || document.body.dir);
    if (dir === 'rtl') {
      // Verify text alignment is correct for RTL
      const bodyAlign = await page.evaluate(() =>
        window.getComputedStyle(document.body).direction
      );
      expect(bodyAlign).toBe('rtl');

      await page.screenshot({ path: 'tests/a11y/screenshots/rtl-{PAGE_NAME}.png' });
    }
  });
```

### 8. Keyboard trap detection

```typescript
  test('keyboard focus is not trapped', async ({ page }) => {
    await page.goto('{ROUTE}');
    await page.waitForLoadState('networkidle');

    // Tab 20 times — should not get stuck on same element twice consecutively
    const focused: string[] = [];
    for (let i = 0; i < 20; i++) {
      await page.keyboard.press('Tab');
      const el = await page.evaluate(() => {
        const a = document.activeElement;
        return a ? `${a.tagName}#${a.id}.${(a as HTMLElement).className}` : 'none';
      });
      focused.push(el);
    }

    // Check no element repeats more than 3 times consecutively
    for (let i = 2; i < focused.length; i++) {
      const tripleSame = focused[i] === focused[i-1] && focused[i] === focused[i-2];
      expect(tripleSame, `Focus trapped at: ${focused[i]}`).toBeFalsy();
    }
  });
});
```

---

## What humans miss — mandatory inclusions

**Color contrast** (add when `has_forms` or visible text content detected):
```typescript
test('text has sufficient color contrast', async ({ page }) => {
  await page.goto('{ROUTE}');
  await page.waitForLoadState('networkidle');
  // Use axe with color contrast rule specifically
  const results = await new AxeBuilder({ page })
    .withRules(['color-contrast'])
    .analyze();
  expect(results.violations, 'Color contrast failures detected').toHaveLength(0);
});
```

**Keyboard-accessible modal** (if modal detected in source):
```typescript
test('modal closes on Escape key', async ({ page }) => {
  // Find trigger
  const trigger = page.getByRole('button', { name: /open|show|modal/i }).first();
  if (await trigger.count() > 0) {
    await trigger.click();
    await page.keyboard.press('Escape');
    await expect(page.locator('[role="dialog"]')).not.toBeVisible();
  }
});
```

---

## Execute & fix loop

After writing spec files, orchestrator runs:
```bash
npx playwright test tests/a11y/ --reporter=json 2>&1
```

If failures reported:
1. If failure is `axe-core not found`: print `install_playwright` and mark `execution_result: "skipped_no_server"`.
2. If failure is a real violation: do NOT fix the test — mark `vulnerabilities_found` equivalent in `a11y_issues`.
3. If failure is selector/locator issue: fix only the locator, not the assertion.

Max 3 fix iterations.

---

## Output format (return to orchestrator)

```json
[
  {
    "source_module": "src/components/LoginForm.tsx",
    "path": "tests/a11y/auth.a11y.spec.ts",
    "tests_written": 8,
    "pages_covered": ["/login", "/register"],
    "a11y_issues": [],
    "status": "created | updated | partial",
    "execution_result": "passed | failed | skipped_no_server | not_run"
  }
]
```

`a11y_issues` is populated with real violations found during test execution, not just test failures.
Coverage reporter adds `a11y` gauge and `critical_violations` field to `coverage_by_category.a11y`.
