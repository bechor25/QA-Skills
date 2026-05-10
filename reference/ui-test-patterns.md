# UI Test Patterns (Playwright)

Reference loaded on demand by `qa-ui-test` agent. Contains code templates for each batch type. Read only the section needed for the detected language.

**Sections by language:**
- TS/JS — `playwright.config.ts`, `@playwright/test`. See "TS/JS Templates" below.
- Python — pytest-playwright. `tests/ui/conftest.py` + per-page `tests/ui/<domain>/test_<page>.py`. See "Python Templates" further down.

`path_contract.expected_files` (passed by orchestrator) is the immutable file list. Sub-agent writes EXACTLY those paths — see qa-ui-test.md HIGHEST PRIORITY block.

---

# TS/JS Templates

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

---

# Python Templates (pytest-playwright)

Python projects use `pytest-playwright`. NO `playwright.config.ts`. Configuration via pytest CLI flags + `tests/ui/conftest.py`.

## tests/ui/conftest.py

```python
import pytest

@pytest.fixture(scope="session")
def base_url():
    import os
    return os.environ.get("BASE_URL", "http://localhost:8000")

@pytest.fixture
def page(page, base_url):
    """Override default page fixture to set baseURL behavior."""
    page.goto = lambda url, **kw: page.__class__.goto(page, url if url.startswith("http") else base_url + url, **kw)
    return page
```

> Do NOT merge addopts into `pytest.ini` / `pyproject.toml` — pollutes other categories.
> UI flags pass on command line only.

## Pytest CLI invocation (mandatory flags)

```bash
cd "${PROJECT_ROOT}" && \
  python3 -m pytest tests/ui/ \
    --screenshot=on \
    --video=retain-on-failure \
    --tracing=retain-on-failure \
    --output=tests/ui/test-results \
    --html=tests/ui/playwright-report/index.html \
    --self-contained-html \
    --json-report --json-report-file=.qa-skills/pytest-ui.json \
    -v
```

`--screenshot=on` produces ≥1 PNG per test → proof-of-run for Phase 9d.2.

## Recon snapshot script (one-off)

```python
# /tmp/qa-recon-{run_id}.py — run with `python3 ... > snapshot.json`
import json, os, sys
from playwright.sync_api import sync_playwright

URL = os.environ["SERVER_URL"]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    snap = {
        "url": page.url,
        "title": page.title(),
        "forms": [{
            "action": f.get_attribute("action"),
            "inputs": [{
                "name": el.get_attribute("name"),
                "id": el.get_attribute("id"),
                "type": el.get_attribute("type"),
                "aria_label": el.get_attribute("aria-label"),
            } for el in f.query_selector_all("input,textarea,select")],
        } for f in page.query_selector_all("form")],
        "buttons": [{"text": b.inner_text().strip(), "aria_label": b.get_attribute("aria-label")}
                    for b in page.query_selector_all("button, [role=button]")],
        "links": [{"href": a.get_attribute("href"), "text": a.inner_text().strip()}
                  for a in page.query_selector_all("a[href]")],
        "html_lang": page.get_attribute("html", "lang"),
        "html_dir":  page.get_attribute("html", "dir"),
    }
    print(json.dumps(snap, indent=2))
    browser.close()
```

## Smoke spec — `tests/ui/test_smoke.py`

```python
from playwright.sync_api import Page, expect

def test_homepage_loads_with_title(page: Page):
    page.goto("/")
    page.wait_for_load_state("networkidle")  # use "load" for SSR
    expect(page).to_have_title(__import__("re").compile(r".+"))
```

## Per-page spec — `tests/ui/<page>/test_<page>.py`

```python
from playwright.sync_api import Page, expect

def test_login_page_loads(page: Page):
    page.goto("/login")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading")).to_be_visible()

def test_login_form_has_email_input(page: Page):
    page.goto("/login")
    expect(page.get_by_label("<EMAIL_LABEL_FROM_RECON>")).to_be_visible()

def test_login_with_valid_credentials(page: Page):
    page.goto("/login")
    page.get_by_label("<EMAIL_LABEL>").fill("test@example.com")
    page.get_by_label("<PASSWORD_LABEL>").fill("TestPass1!")
    page.get_by_role("button", name="<SUBMIT_BUTTON_TEXT>").click()
    page.wait_for_load_state("networkidle")
    expect(page).not_to_have_url(__import__("re").compile(r"login"))

def test_login_with_wrong_credentials_shows_error(page: Page):
    page.goto("/login")
    page.get_by_label("<EMAIL_LABEL>").fill("nobody@nowhere.com")
    page.get_by_label("<PASSWORD_LABEL>").fill("wrong")
    page.get_by_role("button", name="<SUBMIT_BUTTON_TEXT>").click()
    expect(page.get_by_role("alert").or_(page.locator('[aria-invalid="true"]'))).to_be_visible()
```

## Form flow (when non-login form exists)

```python
def test_quote_calculation_displays_result(page: Page):
    page.goto("/quote")
    page.wait_for_load_state("networkidle")
    page.get_by_label("<PRICE_LABEL>").fill("100")
    page.get_by_label("<TAX_LABEL>").fill("17")
    page.get_by_label("<DISCOUNT_LABEL>").fill("10")
    page.get_by_role("button", name="<SUBMIT_BUTTON_TEXT>").click()
    expect(page.locator("[aria-live]")).to_be_visible()

def test_empty_form_shows_validation(page: Page):
    page.goto("/quote")
    page.get_by_role("button", name="<SUBMIT_BUTTON_TEXT>").click()
    expect(page.get_by_role("alert").or_(page.locator('[aria-invalid="true"]'))).to_be_visible()
```

## Navigation tests

```python
def test_nav_login_link_navigates(page: Page):
    page.goto("/")
    page.get_by_role("link", name="<LOGIN_LINK_TEXT>").click()
    expect(page).to_have_url(__import__("re").compile(r"/login"))
```

## Optional: route mocking (Python — only if user opts in)

```python
def test_shows_error_on_api_failure(page: Page):
    page.route("**/api/**", lambda r: r.fulfill(status=500, body='{"error":"down"}'))
    page.goto("/dashboard")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text(__import__("re").compile(r"error|שגיאה", flags=__import__("re").I))).to_be_visible()
```

## Optional: visual regression (Python)

`pytest-playwright` does NOT support `to_have_screenshot`. Use `pixelmatch` or `pillow` manually. Skip unless explicitly enabled.
