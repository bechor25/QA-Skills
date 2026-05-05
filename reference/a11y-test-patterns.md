# Accessibility Test Patterns (WCAG 2.1 AA)

Reference loaded on demand by `qa-a11y-test` agent. Read only the section needed.

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
