---
name: ui-playwright
description: >
  Generate E2E browser tests using Playwright for frontend applications.
  Covers: multi-step flows, form submission, accessibility, visual regression, loading states,
  error states, session expiry, keyboard navigation.
  Supports React, Vue, Angular, HTML+JS, and server-rendered templates.
  Normally invoked by test-orchestrator as part of a full test run.
  Also usable standalone when the user asks to test frontend/UI directly.

  English triggers (standalone): "write UI tests", "test my frontend", "E2E tests",
  "Playwright tests", "test the login flow", "check accessibility", "browser tests",
  "test user flows", "test the UI", "write end-to-end tests".

  Hebrew triggers (עברית): "כתוב בדיקות UI", "בדוק את הממשק שלי", "בדיקות E2E",
  "בדיקות Playwright", "בדוק את זרימת הלוגין", "בדוק נגישות", "בדיקות דפדפן",
  "בדוק זרימות משתמש", "בדיקות ממשק גרפי", "בדיקות end-to-end".
---

# ui-playwright

Generates Playwright E2E tests for frontend files and user flows found by `code-analyzer`.

> **User-facing messages**: use `get_message(key, locale, **kwargs)` from
> `skills/_shared/validate.py`. Never hardcode strings the tester sees.

## Inputs

Receives from `test-orchestrator`:
```json
{
  "frontend_files": [/* frontend_files from code-analyzer */],
  "routes": [/* routes that serve HTML/pages */],
  "project_root": "string",
  "language": "string"
}
```

## Output location

```
{project_root}/tests/e2e/{flow-name}.spec.ts

Examples:
  Login flow     → tests/e2e/auth-login.spec.ts
  User profile   → tests/e2e/user-profile.spec.ts
  Checkout flow  → tests/e2e/checkout.spec.ts
```

## Setup check

Before generating tests, verify Playwright is installed:
```bash
# Check package.json or requirements.txt for playwright
# If missing, print:
echo "Install Playwright first:"
echo "  npm install -D @playwright/test && npx playwright install"
echo "  # or: pip install playwright && playwright install"
```

Generate a `playwright.config.ts` if one doesn't exist:
```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox',  use: { browserName: 'firefox' } },
  ],
});
```

## Phase 1 — Reconnaissance (always first)

Before writing any test, inspect the live page:
```typescript
// Always wait for full network idle before inspecting
await page.goto(url);
await page.waitForLoadState('networkidle');

// Capture page structure for test generation
const title = await page.title();
const forms = await page.locator('form').all();
const buttons = await page.locator('button, [role="button"]').all();
const links = await page.locator('a[href]').all();
const inputs = await page.locator('input, textarea, select').all();
```

If app is not running, generate tests based on code analysis alone and add a comment:
```typescript
// NOTE: Generated from static analysis — run against live app to validate
```

## Multi-step flow tests

Infer flows from route structure and component names. Always test complete flows, not isolated elements.

### Auth flow
```typescript
test('login → dashboard → logout', async ({ page }) => {
  // Step 1: Navigate to login
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  
  // Step 2: Fill form
  await page.getByLabel(/email/i).fill('test@example.com');
  await page.getByLabel(/password/i).fill('TestPass1!');
  
  // Step 3: Submit
  await page.getByRole('button', { name: /sign in|log in|submit/i }).click();
  
  // Step 4: Verify redirect
  await expect(page).toHaveURL(/dashboard|home/);
  await page.waitForLoadState('networkidle');
  
  // Step 5: Verify user state visible
  await expect(page.getByText(/welcome|hello/i)).toBeVisible();
  
  // Step 6: Logout
  await page.getByRole('button', { name: /logout|sign out/i }).click();
  await expect(page).toHaveURL(/login|home|\//);
});
```

### Form submission flow
```typescript
test('form fill → submit → confirmation', async ({ page }) => {
  await page.goto('/form-page');
  await page.waitForLoadState('networkidle');
  
  // Fill all required fields
  for (const input of await page.locator('input[required]').all()) {
    const type = await input.getAttribute('type');
    if (type === 'email') await input.fill('test@example.com');
    else if (type === 'number') await input.fill('42');
    else await input.fill('Test Value');
  }
  
  // Submit
  await page.getByRole('button', { name: /submit|save|create/i }).click();
  
  // Confirm success state
  await expect(
    page.getByText(/success|submitted|saved|thank you/i)
  ).toBeVisible({ timeout: 5000 });
  
  // Verify back-navigation doesn't re-submit
  await page.goBack();
  await expect(page.getByRole('button', { name: /submit/i })).toBeEnabled();
});
```

## Visual regression

Capture baseline screenshots and compare across runs:
```typescript
test('homepage visual regression', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  
  // Hide dynamic content (timestamps, ads) before screenshot
  await page.addStyleTag({ content: '[data-testid="timestamp"] { visibility: hidden }' });
  
  await expect(page).toHaveScreenshot('homepage-baseline.png', {
    maxDiffPixelRatio: 0.02,  // allow 2% difference
  });
});
```

## Accessibility checks (mandatory in every spec file)

```typescript
test('all interactive elements have accessible names', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  
  // Buttons must have text or aria-label
  for (const btn of await page.locator('button').all()) {
    const text = await btn.innerText();
    const label = await btn.getAttribute('aria-label');
    const title = await btn.getAttribute('title');
    expect(text || label || title, 
      `Button missing accessible name: ${await btn.outerHTML()}`
    ).toBeTruthy();
  }
  
  // Images must have alt text
  for (const img of await page.locator('img').all()) {
    const alt = await img.getAttribute('alt');
    expect(alt, `Image missing alt: ${await img.getAttribute('src')}`).not.toBeNull();
  }
  
  // Form inputs must have labels
  for (const input of await page.locator('input:not([type="hidden"])').all()) {
    const id = await input.getAttribute('id');
    const ariaLabel = await input.getAttribute('aria-label');
    const ariaLabelledBy = await input.getAttribute('aria-labelledby');
    const label = id ? await page.locator(`label[for="${id}"]`).count() : 0;
    expect(label > 0 || ariaLabel || ariaLabelledBy,
      `Input missing label: ${await input.getAttribute('name')}`
    ).toBeTruthy();
  }
});

test('keyboard navigation works', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  
  // Tab through all focusable elements
  await page.keyboard.press('Tab');
  const focused1 = await page.locator(':focus').count();
  expect(focused1).toBe(1);
  
  await page.keyboard.press('Tab');
  const focused2 = page.locator(':focus');
  // Each tab moves focus
  await expect(focused2).toBeFocused();
});
```

## Additional "what testers miss" — Phase 8 additions

**Browser back/forward and refresh — form state**:
```typescript
test('browser back does not re-submit form', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel(/email/i).fill('test@example.com');
  await page.getByLabel(/password/i).fill('TestPass1!');
  await page.getByRole('button', { name: /submit|register/i }).click();
  await page.waitForLoadState('networkidle');
  await page.goBack();
  // Form should be empty or show a re-fill state — not auto-submit again
  await expect(page).toHaveURL(/register/);
  const emailValue = await page.getByLabel(/email/i).inputValue().catch(() => '');
  // Should not have pre-filled from previous submission
  expect(emailValue).toBe('');
});

test('page refresh preserves filter/search state via URL', async ({ page }) => {
  await page.goto('/users?search=alice');
  await page.waitForLoadState('networkidle');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(/search=alice/);
});
```

**Multi-tab session invalidation**:
```typescript
test('logout in one tab invalidates other tabs', async ({ browser }) => {
  const context = await browser.newContext();
  const page1 = await context.newPage();
  const page2 = await context.newPage();

  // Login on page1
  await page1.goto('/login');
  await page1.getByLabel(/email/i).fill('user@test.com');
  await page1.getByLabel(/password/i).fill('TestPass1!');
  await page1.getByRole('button', { name: /sign in|log in/i }).click();
  await page1.waitForURL(/dashboard/);

  // Logout on page1
  await page1.getByRole('button', { name: /logout|sign out/i }).click();
  await page1.waitForURL(/login/);

  // page2 should detect session invalidated on next navigation
  await page2.goto('/dashboard');
  await page2.waitForLoadState('networkidle');
  await expect(page2).toHaveURL(/login/);

  await context.close();
});
```

**RTL rendering for Hebrew routes** (critical for this audience):
```typescript
test('Hebrew locale renders RTL correctly', async ({ page }) => {
  // Check if app has Hebrew routes or i18n
  await page.goto('/');
  const htmlDir = await page.getAttribute('html', 'dir');
  const langAttr = await page.getAttribute('html', 'lang');

  if (langAttr?.startsWith('he') || htmlDir === 'rtl') {
    // RTL elements should have text-align: right in computed style
    const bodyDirection = await page.evaluate(() =>
      window.getComputedStyle(document.body).direction
    );
    expect(bodyDirection).toBe('rtl');

    // Take screenshot for visual validation
    await page.screenshot({ path: 'tests/e2e/screenshots/rtl-layout.png', fullPage: true });
  }
});
```

## What humans miss — mandatory inclusions

**Network error handling**:
```typescript
test('shows error state when API fails', async ({ page }) => {
  // Mock API to return 500
  await page.route('**/api/**', route => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'Internal Server Error' }),
  }));
  
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  
  // UI must show error, not blank page or spinner
  await expect(
    page.getByText(/error|something went wrong|try again/i)
  ).toBeVisible();
});
```

**Loading states appear and disappear**:
```typescript
test('loading spinner shows then hides', async ({ page }) => {
  // Slow down API response
  await page.route('**/api/users', async route => {
    await new Promise(r => setTimeout(r, 500));
    await route.continue();
  });
  
  await page.goto('/users');
  
  // Loading state should appear
  await expect(page.getByRole('progressbar').or(page.getByText(/loading/i))).toBeVisible();
  
  // Then disappear
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('progressbar')).not.toBeVisible();
  await expect(page.getByRole('list')).toBeVisible();
});
```

**Form validation messages appear on submit**:
```typescript
test('shows validation errors without submitting', async ({ page }) => {
  await page.goto('/register');
  // Click submit with empty form
  await page.getByRole('button', { name: /submit|register|sign up/i }).click();
  
  // Validation errors must appear inline (not alert boxes)
  await expect(page.getByRole('alert').or(page.locator('[aria-invalid="true"]'))).toBeVisible();
  
  // Should NOT navigate away
  await expect(page).toHaveURL(/register/);
});
```

**Paste into form fields**:
```typescript
test('handles pasted content in inputs', async ({ page }) => {
  await page.goto('/login');
  const emailInput = page.getByLabel(/email/i);
  await emailInput.click();
  await page.keyboard.insertText('pasted@example.com');
  await expect(emailInput).toHaveValue('pasted@example.com');
});
```

**Session expiry — UI redirects correctly**:
```typescript
test('expired session redirects to login', async ({ page, context }) => {
  // Set up authenticated session
  await context.addCookies([{ name: 'session', value: 'EXPIRED_TOKEN', url: 'http://localhost:3000' }]);
  
  // Mock auth endpoint to return 401
  await page.route('**/api/**', route => route.fulfill({ status: 401 }));
  
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  
  // Must redirect to login
  await expect(page).toHaveURL(/login/);
});
```

## Page Object Model

For complex flows, generate a Page Object:
```typescript
// tests/e2e/pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}
  
  async goto() { await this.page.goto('/login'); }
  
  async login(email: string, password: string) {
    await this.page.getByLabel(/email/i).fill(email);
    await this.page.getByLabel(/password/i).fill(password);
    await this.page.getByRole('button', { name: /sign in|log in/i }).click();
    await this.page.waitForLoadState('networkidle');
  }
  
  async expectErrorMessage(text: string | RegExp) {
    await expect(this.page.getByRole('alert')).toContainText(text);
  }
}
```

## Execute & fix loop

Playwright tests require a running server. Before running:
1. Check if `baseURL` is configured in `playwright.config.ts`
2. If server not running: start it (`npm start` / `uvicorn` / `mvn spring-boot:run`) before Playwright, stop after
3. Run: `npx playwright test --reporter=json 2>&1`

If failures reported:
1. Read failing spec + source component
2. Fix root cause: wrong locator (element changed), wrong route mock URL, wrong expected text
3. Fix **only** the failing test
4. Common Playwright failures: `getByLabel` not finding element (add `exact: false`), `waitForLoadState` timeout (extend), route mock URL pattern too strict

**Never run Playwright tests without a server.** If server cannot be started (no start script, port conflict), skip execution and set `execution_result: "skipped_no_server"`.

Max 3 fix iterations.

## Output format (return to orchestrator)

```json
[
  {
    "source_module": "src/components/LoginForm.tsx",
    "path": "tests/e2e/auth-login.spec.ts",
    "tests_written": 8,
    "flows_covered": ["login", "logout", "session-expiry"],
    "accessibility_checks": true,
    "status": "created | updated | partial",
    "execution_result": "passed | failed | skipped_no_server | not_run"
  }
]
```
