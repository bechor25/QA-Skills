# QA Skills — Usage Guide

---

## English

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

Claude will ask for the project path if you haven't provided one. That's the only question it will ask.

### What happens automatically

```
1. Scans your codebase (all files, all languages)
2. Checks what changed since the last run (skips unchanged files)
3. Generates tests in parallel:
   - Unit tests        → for every function and class
   - API tests         → for every HTTP endpoint
   - UI tests          → for every frontend page/flow (Playwright)
   - Security tests    → for auth, injection, XSS, IDOR, and more
4. Runs all generated tests
5. Fixes failing tests automatically (up to 3 attempts)
6. Opens an HTML coverage report in your browser
```

### What you see at the end

An HTML report with:
- **Coverage gauges** — unit / API / UI / security percentages
- **Module table** — every file, its status (covered / partial / uncovered), links to test files
- **Gaps** — what's missing and why it matters (high / medium / low priority)
- **Blind spots** — things human testers typically miss (timing attacks, race conditions, etc.)
- **Timeline** — what ran, how long it took, what was skipped

### Incremental runs

After the first full run, subsequent runs are fast. Claude remembers which files were already tested
(via `test-state.json`) and only processes files that changed.

To force a full regeneration: `regenerate all tests` or `force full test run`.

### Supported languages and frameworks

| Language | Unit tests | API tests | UI tests | Security tests |
|----------|-----------|-----------|----------|----------------|
| TypeScript / JavaScript | Jest / Vitest | supertest | Playwright | ✓ |
| Python | pytest | httpx | Playwright | ✓ |
| Java | JUnit 5 + Mockito | RestAssured | — | ✓ |
| C# / .NET | NUnit + Moq | HttpClient | — | ✓ |

### Standalone skill use (advanced)

Each skill can also be triggered directly if you only need one type of test:

| What you want | What to say |
|---------------|-------------|
| Only unit tests | `write unit tests for src/auth/login.ts` |
| Only API tests | `test my API endpoints` |
| Only UI tests | `write Playwright tests for my frontend` |
| Only security tests | `run a security audit on my project` |
| Just the report | `open the test report` / `regenerate the HTML report` |
| Analyze structure | `map my project structure` / `show me all endpoints` |

### Files created in your project

```
your-project/
├── test-state.json              ← tracks which files were tested and their hashes
├── test-reports/
│   ├── report-data.json         ← raw coverage data
│   └── report-{name}-{date}.html ← the HTML report (opens automatically)
└── tests/
    ├── unit/                    ← unit test files
    ├── api/                     ← API test files
    ├── e2e/                     ← Playwright E2E tests
    └── security/                ← security test files
```

### Skills in this system (for reference)

| Skill | Role | Direct use? |
|-------|------|-------------|
| `test-orchestrator` | Main entry point | Yes — this is what you use |
| `unit-test` | Generates unit tests | Standalone or via orchestrator |
| `api-test` | Generates API tests | Standalone or via orchestrator |
| `ui-playwright` | Generates Playwright E2E tests | Standalone or via orchestrator |
| `security-test` | Generates security tests | Standalone or via orchestrator |
| `code-analyzer` | Scans codebase structure | Internal (also: "map my project") |
| `coverage-reporter` | Aggregates results | Internal |
| `html-reporter` | Generates HTML report | Internal (also: "open test report") |

---

---

## עברית

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

קלוד ישאל לנתיב הפרויקט אם לא סיפקת אחד. זו השאלה היחידה שהוא ישאל.

### מה קורה אוטומטית

```
1. סורק את הקוד שלך (כל הקבצים, כל השפות)
2. בודק מה השתנה מאז הריצה הקודמת (מדלג על קבצים שלא השתנו)
3. מייצר בדיקות במקביל:
   - בדיקות יחידה   ← לכל פונקציה ומחלקה
   - בדיקות API     ← לכל endpoint HTTP
   - בדיקות UI      ← לכל עמוד/זרימה בממשק (Playwright)
   - בדיקות אבטחה   ← אימות, הזרקות, XSS, IDOR, ועוד
4. מריץ את כל הבדיקות שנוצרו
5. מתקן בדיקות כושלות אוטומטית (עד 3 ניסיונות)
6. פותח דוח כיסוי HTML בדפדפן
```

### מה רואים בסוף

דוח HTML עם:
- **מדדי כיסוי** — אחוזים לכל קטגוריה: יחידה / API / UI / אבטחה
- **טבלת מודולים** — כל קובץ, הסטטוס שלו (מכוסה / חלקי / לא מכוסה), קישורים לקבצי הבדיקות
- **פערים** — מה חסר ולמה זה חשוב (עדיפות גבוהה / בינונית / נמוכה)
- **נקודות עיוורות** — דברים שבודקים אנושיים מחמיצים בדרך כלל (timing attacks, race conditions וכו')
- **ציר זמן** — מה רץ, כמה זמן לקח, מה דולג

### ריצות מצטברות

אחרי הריצה המלאה הראשונה, ריצות עוקבות הן מהירות. קלוד זוכר אילו קבצים כבר נבדקו
(דרך `test-state.json`) ומעבד רק קבצים שהשתנו.

לאלץ בדיקה מחדש של הכל: `הרץ בדיקות מלאות מחדש` או `force full test run`.

### שפות וframeworks נתמכים

| שפה | בדיקות יחידה | בדיקות API | בדיקות UI | בדיקות אבטחה |
|-----|-------------|-----------|----------|--------------|
| TypeScript / JavaScript | Jest / Vitest | supertest | Playwright | ✓ |
| Python | pytest | httpx | Playwright | ✓ |
| Java | JUnit 5 + Mockito | RestAssured | — | ✓ |
| C# / .NET | NUnit + Moq | HttpClient | — | ✓ |

### שימוש עצמאי בסקילים (מתקדם)

כל סקיל יכול גם להיות מופעל ישירות אם רוצים רק סוג אחד של בדיקות:

| מה רוצים | מה לכתוב |
|----------|----------|
| רק בדיקות יחידה | `כתוב בדיקות יחידה ל-src/auth/login.ts` |
| רק בדיקות API | `בדוק את ה-endpoints של ה-API שלי` |
| רק בדיקות UI | `כתוב בדיקות Playwright לממשק שלי` |
| רק בדיקות אבטחה | `הרץ בדיקת אבטחה על הפרויקט שלי` |
| רק הדוח | `פתח את דוח הבדיקות` / `צור מחדש את ה-HTML report` |
| ניתוח מבנה | `מפה את מבנה הפרויקט שלי` / `הצג את כל ה-endpoints` |

### קבצים שנוצרים בפרויקט שלך

```
your-project/
├── test-state.json                ← מעקב אחרי קבצים שנבדקו ו-hash שלהם
├── test-reports/
│   ├── report-data.json           ← נתוני כיסוי גולמיים
│   └── report-{name}-{date}.html  ← דוח HTML (נפתח אוטומטית)
└── tests/
    ├── unit/                      ← קבצי בדיקות יחידה
    ├── api/                       ← קבצי בדיקות API
    ├── e2e/                       ← בדיקות Playwright E2E
    └── security/                  ← קבצי בדיקות אבטחה
```

### הסקילים במערכת (לעיון)

| סקיל | תפקיד | שימוש ישיר? |
|------|--------|------------|
| `test-orchestrator` | נקודת כניסה ראשית | כן — זה מה שאתה משתמש בו |
| `unit-test` | מייצר בדיקות יחידה | עצמאי או דרך orchestrator |
| `api-test` | מייצר בדיקות API | עצמאי או דרך orchestrator |
| `ui-playwright` | מייצר בדיקות Playwright E2E | עצמאי או דרך orchestrator |
| `security-test` | מייצר בדיקות אבטחה | עצמאי או דרך orchestrator |
| `code-analyzer` | סורק מבנה קוד | פנימי (גם: "מפה את הפרויקט") |
| `coverage-reporter` | מרכז תוצאות | פנימי |
| `html-reporter` | מייצר דוח HTML | פנימי (גם: "פתח את הדוח") |
