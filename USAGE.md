# QA Skills — Usage Guide

---

## English

### Installation

```bash
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```

Restart Claude Code after installing.

To update:
```bash
claude plugin marketplace update bechor25/QA-Skills
claude plugin update qa-skills
```

To uninstall:
```bash
claude plugin uninstall qa-skills
```

### What this is

A set of Claude Code skills that automatically generate, run, and report on tests for any codebase.
You type one sentence. Claude does the rest. You get an HTML report in your browser.

### The only skill you talk to: `test-orchestrator`

Everything runs through one entry point. You never need to invoke the other skills manually.

### How to start a test run

Open Claude Code in any project and type any of these:

```
generate tests for my project
write tests for /path/to/my/project
what's my test coverage?
what parts of my code are untested?
update tests after my changes
run tests and show me a report
I need tests
```

For specific test types:
```
test accessibility           ← WCAG 2.1 AA checks
contract test                ← validate API schema
security test                ← OWASP + JWT + SSRF
```

Claude will ask for the project path if you haven't provided one. That's the only question it will ask.

### What happens automatically

```
1. Validates environment  — checks toolchain, test framework, server, disk space
2. Analyzes changes       — git diff to skip trivial edits (comments, whitespace)
3. Scans codebase         — routes, integrations, GraphQL, state machines
4. Generates tests in parallel:
   - Unit tests        → for every function and class
   - API tests         → for every HTTP endpoint
   - UI tests          → for every frontend page/flow (Playwright)
   - Security tests    → for auth, injection, XSS, IDOR, JWT confusion, SSRF
   - Accessibility     → WCAG 2.1 AA via axe-core + keyboard navigation
   - Contract tests    → OpenAPI conformance or golden-master drift
5. Runs all generated tests
6. Fixes failing tests automatically (up to 3 attempts per category)
7. Detects flaky tests    — re-runs 3×, reports cause and fix hint
8. Computes Quality Score (0–100) and opens HTML report in browser
```

If the run is interrupted, Claude will offer to resume from where it stopped (within 24 hours).

### What you see at the end

An HTML report with:
- **Quality Score** — 0–100 overall health signal
- **Coverage gauges** — unit / API / UI / security / accessibility / contract
- **Module table** — every file, status (covered / partial / uncovered), links to test files
- **Flaky tests** — non-deterministic tests with cause and suggested fix
- **Gaps** — what's missing and priority (high / medium / low)
- **Blind spots** — things human testers typically miss (timing attacks, race conditions, RTL, etc.)
- **Timeline** — what ran, how long, what was skipped and why

### Incremental runs

After the first full run, subsequent runs are fast. Claude uses git diff to detect what changed
and classifies changes:

| Change type | Action |
|-------------|--------|
| Comments / whitespace only | Skip — no new tests needed |
| Function body changed | Re-run existing tests, fix failures |
| Function signature / new route | Regenerate tests for that module |
| New file | Generate from scratch |

To force a full regeneration: `regenerate all tests` or `force full test run`.

### Supported languages and frameworks

| Language | Unit tests | API tests | UI tests | Security | Accessibility | Contract |
|----------|-----------|-----------|----------|----------|--------------|---------|
| TypeScript / JavaScript | Jest / Vitest | supertest | Playwright | ✓ | ✓ | ✓ |
| Python | pytest | httpx | Playwright | ✓ | ✓ | ✓ |
| Java | JUnit 5 + Mockito | RestAssured | — | ✓ | — | ✓ |
| C# / .NET | NUnit + Moq | HttpClient | — | ✓ | — | ✓ |

### Standalone skill use (advanced)

Each skill can also be triggered directly if you only need one type of test:

| What you want | What to say |
|---------------|-------------|
| Only unit tests | `write unit tests for src/auth/login.ts` |
| Only API tests | `test my API endpoints` |
| Only UI tests | `write Playwright tests for my frontend` |
| Only security tests | `run a security audit on my project` |
| Only accessibility | `test accessibility` / `WCAG` / `a11y` |
| Only contract tests | `contract test` / `validate API schema` |
| Just the report | `open the test report` / `regenerate the HTML report` |
| Analyze structure | `map my project structure` / `show me all endpoints` |

### Files created in your project

```
your-project/
├── test-state.json              ← tracks tested files, hashes, last run timestamp
├── test-reports/
│   ├── report-data.json         ← raw coverage data
│   └── report-{name}-{date}.html ← the HTML report (opens automatically)
└── tests/
    ├── unit/                    ← unit test files
    ├── api/                     ← API test files
    ├── e2e/                     ← Playwright E2E tests
    ├── security/                ← security test files
    ├── a11y/                    ← accessibility test files
    └── contract/                ← contract test files
```

### Skills reference

| Skill | Role | Direct use? |
|-------|------|-------------|
| `test-orchestrator` | Main entry point | Yes — this is what you use |
| `unit-test` | Unit tests | Standalone or via orchestrator |
| `api-test` | API tests | Standalone or via orchestrator |
| `ui-playwright` | Playwright E2E tests | Standalone or via orchestrator |
| `security-test` | Security tests | Standalone or via orchestrator |
| `accessibility-test` | WCAG 2.1 AA tests | Standalone or via orchestrator |
| `contract-test` | API schema conformance | Standalone or via orchestrator |
| `flaky-detector` | Detects non-deterministic tests | Internal |
| `env-validator` | Validates toolchain + environment | Internal |
| `git-diff-analyzer` | Classifies code changes | Internal |
| `code-analyzer` | Scans codebase structure | Internal |
| `coverage-reporter` | Aggregates results + Quality Score | Internal |
| `html-reporter` | Generates HTML report | Internal |

---

---

## עברית

### התקנה

```bash
claude plugin marketplace add bechor25/QA-Skills
claude plugin install qa-skills
```

הפעל מחדש את Claude Code אחרי ההתקנה.

עדכון:
```bash
claude plugin marketplace update bechor25/QA-Skills
claude plugin update qa-skills
```

הסרה:
```bash
claude plugin uninstall qa-skills
```

### מה זה

סט של skills לקלוד קוד שמייצרים, מריצים, ומדווחים על בדיקות לכל פרויקט קוד.
אתה כותב משפט אחד. קלוד עושה הכל. אתה מקבל דוח HTML בדפדפן.

### הסקיל היחיד שאתה מדבר איתו: `test-orchestrator`

כל הזרימה עוברת דרך נקודת כניסה אחת. אין צורך להפעיל שאר הסקילים ידנית.

### איך להתחיל ריצת בדיקות

פתח Claude Code בכל פרויקט והקלד אחד מאלה:

```
צור בדיקות לפרויקט שלי
כתוב בדיקות ל-/נתיב/לפרויקט/שלי
מה הכיסוי של הבדיקות שלי?
מה לא נבדק בקוד?
עדכן בדיקות אחרי השינויים שלי
הרץ בדיקות ותציג לי דוח
אני רוצה בדיקות
```

לסוגי בדיקות ספציפיים:
```
בדוק נגישות         ← בדיקות WCAG 2.1 AA
בדיקות חוזה         ← ולידציית schema של API
בדיקות אבטחה        ← OWASP + JWT + SSRF
```

קלוד ישאל לנתיב הפרויקט אם לא סיפקת אחד. זו השאלה היחידה שהוא ישאל.

### מה קורה אוטומטית

```
1. בודק סביבה       — toolchain, test framework, שרת, מקום בדיסק
2. מנתח שינויים     — git diff כדי לדלג על עריכות טריוויאליות (הערות, רווחים)
3. סורק קוד         — routes, integrations, GraphQL, state machines
4. מייצר בדיקות במקביל:
   - בדיקות יחידה   ← לכל פונקציה ומחלקה
   - בדיקות API     ← לכל endpoint HTTP
   - בדיקות UI      ← לכל עמוד/זרימה בממשק (Playwright)
   - בדיקות אבטחה   ← אימות, הזרקות, XSS, IDOR, JWT confusion, SSRF
   - נגישות         ← WCAG 2.1 AA דרך axe-core + ניווט מקלדת
   - חוזה           ← התאמה ל-OpenAPI או גילוי סטייה מ-golden master
5. מריץ את כל הבדיקות
6. מתקן בדיקות כושלות אוטומטית (עד 3 ניסיונות לכל קטגוריה)
7. מגלה בדיקות flaky — מריץ שוב 3×, מדווח על סיבה ורמז לתיקון
8. מחשב Quality Score (0–100) ופותח דוח HTML בדפדפן
```

אם הריצה הופסקה באמצע — קלוד יציע להמשיך מאיפה שהפסיק (בתוך 24 שעות).

### מה רואים בסוף

דוח HTML עם:
- **Quality Score** — ציון בריאות כולל 0–100
- **מדדי כיסוי** — יחידה / API / UI / אבטחה / נגישות / חוזה
- **טבלת מודולים** — כל קובץ, סטטוס, קישורים לקבצי בדיקות
- **בדיקות flaky** — בדיקות לא יציבות עם סיבה ורמז לתיקון
- **פערים** — מה חסר ועדיפות (גבוהה / בינונית / נמוכה)
- **נקודות עיוורות** — דברים שבודקים אנושיים מחמיצים (timing attacks, race conditions, RTL וכו')
- **ציר זמן** — מה רץ, כמה זמן, מה דולג ולמה

### ריצות מצטברות

אחרי הריצה המלאה הראשונה, ריצות עוקבות הן מהירות. קלוד משתמש ב-git diff כדי לזהות מה השתנה:

| סוג שינוי | פעולה |
|-----------|-------|
| הערות / רווחים בלבד | דילוג — לא צריך בדיקות חדשות |
| גוף הפונקציה השתנה | הרצת בדיקות קיימות, תיקון כשלים |
| חתימת פונקציה / route חדש | יצירת בדיקות מחדש למודול |
| קובץ חדש | יצירה מאפס |

לאלץ בדיקה מחדש של הכל: `הרץ בדיקות מלאות מחדש` או `force full test run`.

### שפות וframeworks נתמכים

| שפה | בדיקות יחידה | בדיקות API | בדיקות UI | אבטחה | נגישות | חוזה |
|-----|-------------|-----------|----------|-------|--------|------|
| TypeScript / JavaScript | Jest / Vitest | supertest | Playwright | ✓ | ✓ | ✓ |
| Python | pytest | httpx | Playwright | ✓ | ✓ | ✓ |
| Java | JUnit 5 + Mockito | RestAssured | — | ✓ | — | ✓ |
| C# / .NET | NUnit + Moq | HttpClient | — | ✓ | — | ✓ |

### שימוש עצמאי בסקילים (מתקדם)

כל סקיל יכול גם להיות מופעל ישירות:

| מה רוצים | מה לכתוב |
|----------|----------|
| רק בדיקות יחידה | `כתוב בדיקות יחידה ל-src/auth/login.ts` |
| רק בדיקות API | `בדוק את ה-endpoints של ה-API שלי` |
| רק בדיקות UI | `כתוב בדיקות Playwright לממשק שלי` |
| רק בדיקות אבטחה | `הרץ בדיקת אבטחה על הפרויקט שלי` |
| רק נגישות | `בדוק נגישות` / `WCAG` / `a11y` |
| רק בדיקות חוזה | `בדיקות חוזה` / `בדוק schema` |
| רק הדוח | `פתח את דוח הבדיקות` / `צור מחדש את ה-HTML report` |
| ניתוח מבנה | `מפה את מבנה הפרויקט שלי` / `הצג את כל ה-endpoints` |

### קבצים שנוצרים בפרויקט שלך

```
your-project/
├── test-state.json                ← מעקב אחרי קבצים שנבדקו, hash, חותמת זמן
├── test-reports/
│   ├── report-data.json           ← נתוני כיסוי גולמיים
│   └── report-{name}-{date}.html  ← דוח HTML (נפתח אוטומטית)
└── tests/
    ├── unit/                      ← בדיקות יחידה
    ├── api/                       ← בדיקות API
    ├── e2e/                       ← בדיקות Playwright E2E
    ├── security/                  ← בדיקות אבטחה
    ├── a11y/                      ← בדיקות נגישות
    └── contract/                  ← בדיקות חוזה
```

### הסקילים במערכת (לעיון)

| סקיל | תפקיד | שימוש ישיר? |
|------|--------|------------|
| `test-orchestrator` | נקודת כניסה ראשית | כן — זה מה שאתה משתמש בו |
| `unit-test` | בדיקות יחידה | עצמאי או דרך orchestrator |
| `api-test` | בדיקות API | עצמאי או דרך orchestrator |
| `ui-playwright` | בדיקות Playwright E2E | עצמאי או דרך orchestrator |
| `security-test` | בדיקות אבטחה | עצמאי או דרך orchestrator |
| `accessibility-test` | בדיקות WCAG 2.1 AA | עצמאי או דרך orchestrator |
| `contract-test` | התאמת schema של API | עצמאי או דרך orchestrator |
| `flaky-detector` | גילוי בדיקות לא יציבות | פנימי |
| `env-validator` | בדיקת toolchain וסביבה | פנימי |
| `git-diff-analyzer` | סיווג שינויי קוד | פנימי |
| `code-analyzer` | סריקת מבנה קוד | פנימי |
| `coverage-reporter` | ריכוז תוצאות + Quality Score | פנימי |
| `html-reporter` | יצירת דוח HTML | פנימי |
