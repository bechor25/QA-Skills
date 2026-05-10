# UI Test Patterns (Playwright)

Reference loaded on demand by `qa-ui-test` agent. Contains code templates for each batch type. Read only the section needed.

## playwright.config.ts (template)

```typescript
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/ui/e2e',
  outputDir: './tests/ui/test-results',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    headless: true,
    screenshot: 'on',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
  },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'tests/ui/playwright-report' }]],
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
```

## Reconnaissance script (`/tmp/qa-recon-{run_id}.ts`)

```typescript
import { chromium } from 'playwright';
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(process.env.SERVER_URL!);
  await page.waitForLoadState('networkidle');
  const snapshot = {
    url: page.url(),
    title: await page.title(),
    forms: await page.$$eval('form', forms => forms.map(f => ({
      action: f.action,
      inputs: Array.from(f.querySelectorAll('input,textarea,select')).map(el => ({
        name: (el as HTMLInputElement).name,
        id: el.id,
        type: (el as HTMLInputElement).type,
        ariaLabel: el.getAttribute('aria-label'),
        labelText: el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent?.trim() : null,
      })),
    }))),
    buttons: await page.$$eval('button, [role=button]', btns => btns.map(b => ({
      text: b.textContent?.trim(), ariaLabel: b.getAttribute('aria-label'),
    }))),
    links: await page.$$eval('a[href]', as => as.map(a => ({
      href: a.getAttribute('href'), text: a.textContent?.trim(),
    }))),
    htmlLang: await page.getAttribute('html', 'lang'),
    htmlDir: await page.getAttribute('html', 'dir'),
  };
  console.log(JSON.stringify(snapshot, null, 2));
  await browser.close();
})();
```

## Smoke spec (Batch 1)

```typescript
import { test, expect } from '@playwright/test';

test('homepage loads with non-empty title', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveTitle(/.+/);
});
```

## Auth flow (Batch 2 — only if login form exists in recon)

```typescript
import { test, expect } from '@playwright/test';

test.describe('auth flow', () => {
  test('login → dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.getByLabel('<EMAIL_LABEL_FROM_RECON>').fill('test@example.com');
    await page.getByLabel('<PASSWORD_LABEL_FROM_RECON>').fill('TestPass1!');
    await page.getByRole('button', { name: '<SUBMIT_BUTTON_TEXT_FROM_RECON>' }).click();
    await page.waitForLoadState('networkidle');
    // Replace with a known post-login indicator from recon
    await expect(page).not.toHaveURL(/login/);
  });

  test('invalid credentials show error', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('<EMAIL_LABEL>').fill('nobody@nowhere.com');
    await page.getByLabel('<PASSWORD_LABEL>').fill('wrong');
    await page.getByRole('button', { name: '<SUBMIT_BUTTON_TEXT>' }).click();
    // App must show some error indicator (alert role or aria-invalid)
    await expect(page.getByRole('alert').or(page.locator('[aria-invalid="true"]'))).toBeVisible();
  });

  test('logout returns to login', async ({ page }) => {
    // Login first using shared helper or stored auth state
    await page.goto('/dashboard');
    await page.getByRole('button', { name: /logout|sign out|התנתק/i }).click();
    await expect(page).toHaveURL(/login|^\/$/);
  });
});
```

## Form flow (Batch 3 — only if non-login form exists in recon)

```typescript
import { test, expect } from '@playwright/test';

test('form fill → submit → success', async ({ page }) => {
  await page.goto('<FORM_PAGE_FROM_RECON>');
  await page.waitForLoadState('networkidle');
  // Use concrete labels from recon — never regex guesses
  await page.getByLabel('<FIELD_1_LABEL>').fill('Sample value');
  await page.getByLabel('<FIELD_2_LABEL>').fill('test@example.com');
  await page.getByRole('button', { name: '<SUBMIT_BUTTON_TEXT>' }).click();
  await expect(page.getByText(/success|saved|submitted|נשמר|נשלח/i)).toBeVisible({ timeout: 5000 });
});

test('empty form shows validation', async ({ page }) => {
  await page.goto('<FORM_PAGE_FROM_RECON>');
  await page.getByRole('button', { name: '<SUBMIT_BUTTON_TEXT>' }).click();
  await expect(page.getByRole('alert').or(page.locator('[aria-invalid="true"]'))).toBeVisible();
});
```

## a11y_basic (Batch 4)

```typescript
import { test, expect } from '@playwright/test';

test('all buttons have accessible name', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const buttons = await page.locator('button').all();
  for (const btn of buttons) {
    const text = await btn.innerText();
    const aria = await btn.getAttribute('aria-label');
    expect(text || aria, 'button missing accessible name').toBeTruthy();
  }
});

test('keyboard tab moves focus through interactive elements', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toBeFocused();
});
```

## Optional batches

### visual_regression (only if user opts in)
```typescript
test('homepage visual', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.addStyleTag({ content: '[data-testid="timestamp"] { visibility: hidden }' });
  await expect(page).toHaveScreenshot('homepage.png', { maxDiffPixelRatio: 0.02 });
});
```
First run requires `--update-snapshots`.

### multi_tab (only if auth flow passed AND user opts in)
```typescript
test('logout in tab1 invalidates tab2', async ({ browser }) => {
  const ctx = await browser.newContext();
  const p1 = await ctx.newPage();
  const p2 = await ctx.newPage();
  await loginViaUI(p1);
  await p2.goto('/dashboard');
  await p1.getByRole('button', { name: /logout/i }).click();
  await p2.goto('/dashboard');
  await expect(p2).toHaveURL(/login/);
  await ctx.close();
});
```

### route_mocks (only if user opts in)
```typescript
test('shows error on API failure', async ({ page }) => {
  await page.route('**/api/**', r => r.fulfill({ status: 500, body: '{"error":"down"}' }));
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText(/error|something went wrong|try again|שגיאה/i)).toBeVisible();
});
```

## Page Object Model (when flow has 4+ steps)

```typescript
export class LoginPage {
  constructor(private page: Page) {}
  async goto() { await this.page.goto('/login'); }
  async login(email: string, password: string) {
    await this.page.getByLabel('Email').fill(email);
    await this.page.getByLabel('Password').fill(password);
    await this.page.getByRole('button', { name: 'Sign in' }).click();
    await this.page.waitForLoadState('networkidle');
  }
}
```
