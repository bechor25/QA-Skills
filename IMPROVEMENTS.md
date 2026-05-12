# QA-Skills Improvement Plan

מבוסס על ניתוח ריצה על `Candidate_Mngmnt` (2026-05-12). Score=30, 0/14 passed.

## בעיות שזוהו

| # | Layer | Issue | Impact |
|---|-------|-------|--------|
| 1 | Generator | תבנית קשיחה — כל טסט קורא `GET /` במקום route אמיתי | כל ה-API tests חסרי משמעות |
| 2 | Generator | Import קשיח `../../../src/server` — לא קיים ב-monorepo | jest קורס בייבוא |
| 3 | Generator | אין app entry detection (monorepo/workspaces) | tests לא מקומפלים |
| 4 | Generator | UI tests = `goto /` בלבד, אין selectors מ-`ui_scanner` | UI tests חסרי ערך |
| 5 | Generator | Security tests זהים, payload יחיד לכל route | אין כיסוי OWASP אמיתי |
| 6 | Critic | ציון 10/10 לכל קובץ — בודק רק vacuous patterns | אין שער איכות |
| 7 | Critic | לא מריץ `tsc --noEmit` / לא מוודא שה-import resolves | טסטים שבורים מקבלים pass |
| 8 | Executor | `exit=1 + parsed=0` לא מסווג כ-runner-crash | healing לא מטפל |
| 9 | Coverage | מציג 100% כיסוי גם כששום טסט לא עבר | מטריקה מטעה |

## משימות (סדר ביצוע)

### Phase 1 — Generator יקבל route concrete

- [ ] **T1.1** הרחבת `schemas.Scenario` להכיל `route: RouteEntry | None`
- [ ] **T1.2** ב-`scenario_builder`: חיבור scenario ל-route מתוך `api.routes`
- [ ] **T1.3** ב-`api_tests._jest_file`: שימוש ב-`sc.route.method` + `sc.route.pattern` במקום `GET /`
- [ ] **T1.4** ב-`api_tests._pytest_file`: אותו דבר ל-Python
- [ ] **T1.5** טיפול ב-path params (`:id` → `1`, `{id}` → `1`)

### Phase 2 — גילוי app entry נכון

- [ ] **T2.1** מודול חדש `qa_agent/context/app_entry.py`: scan ל-`package.json` → workspaces → find default export of express/fastify
- [ ] **T2.2** שמירת `app_entry` ב-`project_map.json`
- [ ] **T2.3** Generator יקרא `app_entry` ויחשב import path יחסי לתיקיית הטסט
- [ ] **T2.4** fallback: אם לא נמצא — לדלג על ייצור jest tests עם הודעה ב-log

### Phase 3 — Critic מחמיר

- [ ] **T3.1** validator חדש `qa_agent/quality/import_validator.py`: בדיקה ש-import resolves (`Path.exists` יחסית לקובץ)
- [ ] **T3.2** validator חדש `qa_agent/quality/compile_validator.py`: הרצת `tsc --noEmit` על קבצי TS (אופציונלי, רק אם tsc זמין)
- [ ] **T3.3** `test_critic._score`: ציון יורד ל-2 אם יש finding מסוג `import-unresolved` או `compile-error`
- [ ] **T3.4** סינון: לא להעביר לביצוע קבצים עם ציון <= 2

### Phase 4 — Executor + Healing משופרים

- [ ] **T4.1** `jest_runner._parse_jest_json`: זיהוי "no tests found / runtime error" → סיווג כ-`runner-crash`
- [ ] **T4.2** `healing/classifiers.py`: קטגוריה חדשה `import-path` (regex על `Cannot find module`)
- [ ] **T4.3** `healing/policies.py`: action חדש `fix-import-path`
- [ ] **T4.4** `healing/engine.py`: יישום של `fix-import-path` — חיפוש app entry אמיתי והחלפת ה-import

### Phase 5 — UI & Security איכותיים

- [ ] **T5.1** `ui_tests`: שימוש ב-`ui_scanner` selectors (data-testid, role, text) במקום generic
- [ ] **T5.2** `security_tests`: payload מותאם לפי route — params → SQLi, body → XSS, auth → token tampering
- [ ] **T5.3** הפרדה לפי OWASP category: A01/A03/A07 — תבנית שונה לכל אחת

### Phase 6 — Coverage metric אמיתי

- [ ] **T6.1** `coverage.py`: הוספת `effective_coverage = passed / planned`
- [ ] **T6.2** report.html: הצגת effective coverage לצד planned coverage

## קריטריון הצלחה

הרצה חוזרת על `Candidate_Mngmnt` תניב:
- ≥ 50% מהטסטים שנוצרים מקומפלים (tsc clean)
- ≥ 30% עוברים בפועל (לא 0)
- Score כולל ≥ 60 (לעומת 30 כיום)
- Critic נותן ציונים מגוונים (לא רק 10)

---

## תוצאות לאחר ביצוע (2026-05-12 09:15)

### השוואה לפני/אחרי

| מדד | לפני | אחרי |
|-----|------|------|
| App entry detection | אין | מזהה `apps/api/src/app.ts` (express) אוטומטית |
| API tests target | `GET /` לכולם | route ספציפי: `GET /sso/login`, `POST /users` וכו' |
| Import path | `../../../src/server` (שבור) | `../../../qa-agent.app` (shim) |
| Jest TS transform | חסר | `ts-jest` preset + ESM `.js` mapper |
| Security tests runner | playwright (שגוי) | jest+supertest |
| Failed counter on jest crash | `0` (silent) | `len(test_files)` (גלוי) |
| Effective coverage | לא נמדד | מוצג בדוח |
| Path params | לא מטופלים | `:id`→`1`, `{slug}`→`sample` |

### מה רץ עכשיו

ההרצה האחרונה (`runs/20260512T061501Z-7ac53d`):
- 31 קבצי טסטים נוצרו וכולם מקומפלים
- shim `qa-agent.app.ts` נוצר + `jest.qa-agent.config.cjs`
- 32/32 הטסטים מבוצעים (`executed=32, failed=32`)
- Healing מסווג את הכשלים נכון

### הסיבה לכך ש-Score עדיין 30

נחשפו בעיות **ספציפיות לפרויקט** שלא ניתן לפתור גנרית:

1. **Env validation on import** — `apps/api/src/config/env.ts` קורא `process.exit(1)` אם חסר `DATABASE_URL`/`JWT_SECRET` מינימום 32 תווים וכו'
2. **TS path aliases** — `@ats/shared` ב-`tsconfig.base.json` paths, jest לא מודע
3. **External services** — האפליקציה דורשת postgres + redis בריצה

### Phase 7 (work נוסף — לא בוצע)

- [ ] **T7.1** קריאת `tsconfig.base.json` paths → תרגום ל-jest `moduleNameMapper`
- [ ] **T7.2** זיהוי `.env.example` → טעינת ערכי placeholder ל-`process.env` לפני import
- [ ] **T7.3** מצב "external mode" — בדיקות מול שרת רץ (`QA_BASE_URL`) במקום in-process import
- [ ] **T7.4** LLM-augmented generation — חיבור ל-Anthropic API לקריאת הקוד וייצור tests עם הקשר אמיתי
