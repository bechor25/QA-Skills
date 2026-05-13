# Work Plan — QA Pipeline Fixes

נוצר: 2026-05-12
תאריך יעד: ריצה מלאה ירוקה על `Candidate_Mngmnt` (Vite+React+Express+Prisma monorepo)

---

## רקע — בעיות שזוהו בריצה אחרונה

| # | בעיה | עדות |
|---|---|---|
| 1 | UI/a11y מתים — 0 tests מתוך 248 | `pm.frameworks=[]` כי tech_stack לא רואה monorepo |
| 2 | mapper-agent זיהם cap (workflows עם 20 modules) | `capability_map.json` workflows.route_globs |
| 3 | 15 route files נשמטו (`auth.ts`, `users.ts`, ...) | רק 20/35 modules ב-contracts |
| 4 | Clusterer יוצר caps פייק לפי URL prefix | `raw_capability_map.json` עם 20 caps כמו `me`, `saved`, `exports` |
| 5 | body-author רץ סדרתי — 19% completion (47/248) | distribution stubs alphabetical |
| 6 | 248 קבצים = file-per-scenario, קיצוני | 1 spec.ts per scenario במקום grouping |

---

## רשימת תיקונים

### Fix A — tech_stack monorepo aware

**קובץ:** [qa_agent/scanners/tech_stack.py](qa_agent/scanners/tech_stack.py)

**שינוי:**
- `_read_npm_deps(root)` יקרא גם:
  - `<root>/package.json`
  - workspaces lookup (npm/yarn/pnpm workspaces, lerna packages)
  - fallback: `<root>/apps/*/package.json`, `<root>/packages/*/package.json`
- merge dependency maps — אם framework existing במספר packages, evidence מצטבר

**קריטריון QA:** `pm.frameworks` כולל `React`+`Vite` כשרצים על Candidate_Mngmnt.

---

### Fix B — ui_scanner גנרי

**קובץ:** [qa_agent/scanners/ui_scanner.py](qa_agent/scanners/ui_scanner.py)

**שינוי:**
- הוסף `_scan_react_router(root, pm)` — מופעל כש-`React` ב-frameworks (לא רק Next).
- מקור routes: parse `<Route path="..." element={<Component />} />` מ-React Router DOM v6 syntax (regex על `.tsx/.jsx` קבצים).
- mapping: `path` → `route`, component import → `source_path`.
- אם אין router config — fallback סריקת `**/pages/**/*.tsx` + `**/views/**/*.tsx` (גנרי, לא hardcoded לפרויקט ספציפי).

**קריטריון QA:** `ui_inventory.pages` > 0 על Candidate_Mngmnt (יש Routes ב-App.tsx).

---

### Fix C — clusterer noise filter

**קובץ:** [qa_agent/quality/capability_discovery.py](qa_agent/quality/capability_discovery.py)

**שינויים:**
1. הרחב `_API_PREFIX_NOISE` עם: `me`, `saved`, `exports`, `messages`, `groups`, `roles`, `domains`, `hr-calls`, `divisions`, `contacts`.
2. הוסף canonical caps tier: `auth`, `users`, `permissions` תמיד caps עצמאיים אם יש להם source file matching `auth.ts`/`users.ts`/etc — לא ימוזגו ל-others.
3. drop clusters עם `< 3 routes && < 2 ui_files` (noise threshold).
4. merge sub-prefixes ל-parent: cluster עם `/me/tasks` ימוזג לתוך `tasks` cap.

**קריטריון QA:** raw_capability_map ל-Candidate_Mngmnt כולל `auth` cap, ללא `me`/`saved`/`exports`.

---

### Fix D — mapper-agent prompt rules

**קובץ:** [agents/qa-capability-mapper.md](agents/qa-capability-mapper.md)

**שינויים בguidelines:**
1. **Canonical caps preservation** — אם קיים `auth`, `users`, `permissions` במקור — חובה לשמור כcaps עצמאיים, אסור למזג עם business caps.
2. **Bloat guard** — אסור `route_globs` עם > 5 modules **אלא אם** כולם מאותו business domain (semantic check by name).
3. **Drop-or-merge** — אם cluster לא מתאים לאף קטגוריה ולא יכול להיות cap עצמאי → drop, לא bloat.
4. **Output validation hint** — בסוף, mapper בודק שכל route file מ-raw מופיע ב-route_globs של בדיוק cap אחד.

**קריטריון QA:** mapper-agent על Candidate_Mngmnt → `auth` כ-cap, `workflows.route_globs` כולל רק `workflows.ts`.

---

### Fix E — body-author parallel fan-out

**קובץ:** [skills/test-orchestrator/SKILL.md](skills/test-orchestrator/SKILL.md) phase 7

**שינוי:**
- Phase 7 dispatch matrix: `caps × categories × batches`.
- כל batch (5 scenarios) → Agent call נפרד.
- **כל ה-Agent calls נשלחים בהודעה אחת** (parallel dispatch — לפי הוראת multi-tool-call-in-one-message).
- אסור batch sequence — חייב single message מולטיביל.

**קריטריון QA:** ריצה הבאה — body-author מסיים את כל ה-caps בזמן דומה ל-call יחיד, לא × N.

---

### Fix F — scaffold grouping (file-per-cap-category)

**שלוש קבצים:**

1. **[qa_agent/generators/scaffolds.py](qa_agent/generators/scaffolds.py)**
   - `emit_scaffold` משנה signature: מקבל `(cap, category, scenarios: list[RichScenario])` → file יחיד.
   - בונה `describe("<cap> — <category>", () => { ... })` עם `it.todo("scenario_id: title")` per scenario.
   - filename: `tests/qa-agent/<category>/<cap>.spec.ts`.

2. **[qa_agent/cli/commands/scaffold.py](qa_agent/cli/commands/scaffold.py)**
   - group scenarios by `(capability, category)` לפני dispatch.
   - per group → קריאה אחת ל-`emit_scaffold`.

3. **[agents/qa-body-author.md](agents/qa-body-author.md)**
   - Input contract: file path + list of stub markers (scenario_ids) במקום scenario יחיד.
   - יחליף כל `it.todo` באותו file לפי scenario_id.
   - Output: same file path, multiple it() blocks filled.

**קריטריון QA:**
- ~33 spec.ts files במקום 248 (11 caps × 3 categories, plus ui+a11y אחרי A+B).
- כל file עם describe + N×it.

---

## סדר ביצוע

| Step | Fix | תלות |
|---|---|---|
| 1 | F (grouping) | אין — בסיס |
| 2 | C (clusterer noise) | אין |
| 3 | A (tech_stack monorepo) | אין |
| 4 | B (ui_scanner generic) | A |
| 5 | D (mapper prompt) | C |
| 6 | E (body parallel) | F |

**Logical order:** F → C → A → B → D → E.

---

## Validation gates

לאחר כל fix:

```bash
# unit + lint
cd /Users/bechorsimhaev/Desktop/code/QA-Skills
pytest tests/ -x  # אם יש; אחרת skip
ruff check qa_agent/
```

לאחר **כל** ה-fixes (E2E):

```bash
qa-skills-prepare --project /Users/bechorsimhaev/Desktop/code/Candidate_Mngmnt
# /qa-skills:test-orchestrator (manual)
# בדיקות acceptance:
```

**Acceptance criteria:**

| # | בדיקה | יעד |
|---|---|---|
| 1 | `pm.frameworks` | כולל `React`, `Vite` |
| 2 | `ui_inventory.pages` | > 0 |
| 3 | `capability_map.json` | `auth` cap קיים, workflows route_globs נקי |
| 4 | `contracts/*.json` ui_entry_points | > 0 בלפחות 3 caps |
| 5 | `scenarios/*.json` categories | כולל `ui` + `accessibility` |
| 6 | `tests/qa-agent/` file count | 25-40 (לא 248) |
| 7 | `tests/qa-agent/ui/` + `accessibility/` | קיים |
| 8 | body-author completion | 100% בריצה אחת (~5 דקות) |

---

## הערות commit/git

- **לא commitים בלי אישור מפורש.**
- כל fix = commit נפרד (אם המשתמש מבקש).
- commit message format: `fix(<area>): <summary>` + Co-Authored-By.

---

## החלטות מאושרות

| נושא | החלטה |
|---|---|
| Fix B fallback | **deps-gated** — מופעל רק כשנמצא `react`+`react-router-dom` או `vue`+`vue-router` בכל package.json במונורפו |
| Fix C threshold | **3 routes** + canonical bypass (`auth`, `users`, `permissions` תמיד שורדים) |
| Fix F categories | **5 categories בלבד** — `api/security/performance/ui/accessibility`. אין `contract` נפרד |

---

## עקרונות מחייבים

1. **אפס ערכים project-specific** — אסור hardcoded paths/names מ-`Candidate_Mngmnt` או כל פרויקט יעד.
2. **Detection over assumption** — deps (package.json/pyproject.toml/requirements.txt) קודמים לסריקת filesystem.
3. **Gated fallbacks** — סריקות גנריות רק כשdeps detection מאשר רלוונטיות.
4. **Convention lists גנריים** — `pages/`, `views/`, `routes/`, `app/` בלבד. אסור project-named.
5. **Mental test** — כל fix נבחן מנטלית מול 3+ project layouts (monorepo/single/custom) לפני סיום.

---

## דו"ח סופי

- **שפה:** עברית.
- **תוכן:** acceptance criteria ✓/✗, מספרי קבצים, coverage per category, runtime per phase, failures triaged.
- **פורמט:** HTML (report skill) + סיכום markdown בעברית בסוף הריצה.

---

# WORKPLAN v2 — Runtime gaps (Fixes G / H / I)

נוצר: 2026-05-13
טריגר: ריצה מלאה על `Candidate_Mngmnt` הניבה 332 בדיקות, **332/332 נכשלו**.

## דיאגנוזה בקצרה

| Layer | פערים שזוהו |
|---|---|
| Test framework | scaffolds מפיקים Jest tests; ה-target משתמש ב-**vitest** בפועל. אין `vitest_runner.py` בכלל ב-qa-agent. |
| Harness | תבניות מייבאות `import app from "../../../qa-agent.app"` — הקובץ אף פעם לא נוצר. תוצאה: module not found לכל api/security/perf. |
| Helpers | UI tests מייבאים `../helpers/api-fixtures` — לא קיים. body-author מציין `// FIXTURE GAP:` ב-72+ קבצים. |
| Runner config | אין `playwright.config.*` ב-target → `page.goto("/...")` בלי `baseURL` נכשל לפני שטסט בכלל מתחיל. |
| Triage visibility | `runs/<id>/logs/` ריקה — אין error context per file. triage עיוור. |

איכות body-author עצמו טובה — הקוד שנכתב נכון מול ה-contract; הכשל הוא בכל ה-**סביבה** שמסביב לטסט.

## עקרון מחייב

**ה-target אינו ניתן לשינוי על ידי qa-skills.** הפלאגין מפיק קבצים *משלימים* תחת `tests/qa-agent/` (וקובץ shim אחד בלבד שזוכה ל-namespace קבוע). אסור לעדכן `package.json`, `playwright.config.ts` קיים, jest config קיים, או כל קובץ מחוץ ל-`tests/qa-agent/` בלי קלט מהמשתמש.

---

## Fix G — Runner-aware scaffolds

### מה נשבר

[qa_agent/generators/scaffolds.py](qa_agent/generators/scaffolds.py) `_GROUP_BUILDERS` ממפה `("api", "typescript") → _api_jest_group` קשיח. אין branch ל-vitest. גם כשה-target מתועד ב-`pm.frameworks` כ-Vitest, scaffold ממשיך לפלוט קוד Jest.

### מה צריך לקרות

1. **גילוי runner per-workspace** ב-[qa_agent/scanners/tech_stack.py](qa_agent/scanners/tech_stack.py):
   - עבור TS — סדר עדיפויות: vitest (deps OR `vitest.config.*` file) > jest (deps + `jest.config.*` file) > none. אם אין שניהם → ברירת מחדל `vitest` (תאימות native ל-TS, אין צורך ב-ts-jest).
   - עבור py — pytest כברירת מחדל (לא משתנה).
   - תוצר: שדה חדש `test_runners: dict[str, str]` ב-`ProjectMap` (api_runner, ui_runner). ה-resolution הוא **דטרמיניסטי**, מבוסס דק על detection.

2. **builders חדשים** ב-`scaffolds.py`:
   - `_api_vitest_group`, `_security_vitest_group`, `_perf_vitest_group`.
   - Body shape כמעט זהה ל-jest, ההבדל הוא:
     - `import { describe, it, expect, beforeEach, afterEach } from "vitest";`
     - `it.todo("...")` נשאר תקין (vitest תומך).
   - הוסף matrix dispatch `(category, language, runner)`.

3. **scaffold command** מעביר `pm.test_runners` ל-`emit_scaffold_group` כך שכל קריאה בוחרת builder לפי הסוג.

### עקרונות

- **אפס hardcoded paths** — runner detection לפי deps + config files; אסור list של פרויקטים.
- **modular** — הוספת runner נוסף (Bun test, Mocha) בעתיד = הוספת entry ל-`_RUNNER_DETECTORS` + builder אחד.

### קבצים שמשתנים / מתווספים

| קובץ | פעולה |
|---|---|
| [qa_agent/scanners/tech_stack.py](qa_agent/scanners/tech_stack.py) | להוסיף runner detection + שדה `test_runners` ב-`ProjectMap` |
| [qa_agent/state/schemas.py](qa_agent/state/schemas.py) | `ProjectMap.test_runners: dict[str, str]` (api/ui keys) |
| [qa_agent/generators/scaffolds.py](qa_agent/generators/scaffolds.py) | מטריצת dispatch לפי runner; builders חדשים לוויטסט |
| [qa_agent/cli/commands/scaffold.py](qa_agent/cli/commands/scaffold.py) | מעביר `pm.test_runners` הלאה |
| [qa_agent/runtime/install_planner.py](qa_agent/runtime/install_planner.py) | מתחשב ב-vitest (לא רק jest); לוגיקה: install רק אם המודול חסר ב-target |

### Acceptance

- ריצה על `Candidate_Mngmnt` → scaffolds פולטים `import { ... } from "vitest"`.
- ריצה על פרויקט Jest מובהק (כל פרויקט עם `jest.config.*` קיים) → scaffolds פולטים `from "@jest/globals"`.

---

## Fix H — Auto-generated harness + helpers

### מה נשבר

3 קבצים חסרים שאליהם scaffolds מצביעים, ועוד אחד שלא נוצר על-ידי qa-agent אלא נדרש על-ידי הרצת UI:

- `qa-agent.app` (root) — re-export של ה-app בפועל. **בכל target.**
- `tests/qa-agent/helpers/api-fixtures.ts` — helper לעיתים.
- `tests/qa-agent/playwright.config.ts` — config עם baseURL ל-UI tests.
- `tests/qa-agent/vitest.config.ts` — config שמכוון את vitest לקבצי `tests/qa-agent/` (כשרץ runner שלנו ולא של ה-target).

### עקרונות מודולריות

1. **Namespace תחת `tests/qa-agent/`** — קבצי harness/config של qa-skills חיים תחת `tests/qa-agent/`. הקובץ היחיד שיכול לגעת ב-root הוא `tests/qa-agent/qa-agent.app.ts` (מועבר מ-root במסגרת fix זה).
2. **Detection over hardcode** — entry של ה-app מתגלה ע"י api_scanner (מי שייצא `app` או `createServer`); baseURL מתגלה מ-`vite.config.*` (server.port) ; fallback ל-env var.
3. **Idempotent** — אם הקובץ כבר קיים, אסור לעדכן/לדרוס. רק יצירה חסר.
4. **Generic stubs** — `api-fixtures.ts` הוא stub עם `cleanup: async () => {}` שהמשתמש יכול לדרוס. אסור project-specific seeding.

### מה יקרה ב-scaffold phase

לאחר phase 6 (כתיבת spec files), [qa_agent/cli/commands/scaffold.py](qa_agent/cli/commands/scaffold.py) ירוץ helper `emit_harness_files(root, pm, generated_tests)`:

1. **`tests/qa-agent/qa-agent.app.ts`**:
   ```ts
   // auto-generated by qa-skills. Edit only if your app entry moves.
   export { default } from "<DETECTED_RELATIVE_PATH>";
   ```
   - מקור הזיהוי: api_scanner מנפיק כיום routes עם `module_path`. ה-entry הוא הקובץ עם הספירה הגבוהה ביותר של `app.use(...)` או `app.listen(...)` (regex), או הקובץ שמייצא default ומכיל `createServer`/`createApp`. אסור hardcode של `src/server.ts` או דומה.
   - אם לא מזוהה — לא נוצר. במקום זה, scaffolds מקבלים `// HARNESS GAP: app entry not detected — set QA_API_APP_PATH env var.`

2. **`tests/qa-agent/playwright.config.ts`** (רק אם UI tests נוצרו ואין `playwright.config.*` ב-target):
   ```ts
   import { defineConfig } from "@playwright/test";
   export default defineConfig({
     testDir: ".",
     use: { baseURL: process.env.QA_BASE_URL ?? "<DETECTED_BASE_URL>" },
   });
   ```
   - DETECTED_BASE_URL: `http://localhost:<vite port>` אם vite.config מגדיר `server.port`; אחרת `http://localhost:5173` (vite default — generic, לא project-specific).
   - אם יש `playwright.config.*` ב-target — לא נוצר; משאירים ל-target.

3. **`tests/qa-agent/vitest.config.ts`** (אם vitest רץ + אין config ב-target שכיוון לטסטים שלנו):
   ```ts
   import { defineConfig } from "vitest/config";
   export default defineConfig({
     test: { include: ["tests/qa-agent/api/**/*.spec.ts",
                       "tests/qa-agent/security/**/*.spec.ts",
                       "tests/qa-agent/performance/**/*.spec.ts"] },
   });
   ```

4. **`tests/qa-agent/helpers/api-fixtures.ts`**:
   ```ts
   /**
    * Default fixture helper. Override per-project by editing this file.
    * The default is a no-op so generated tests load; real seeding is project-specific.
    */
   export async function useApiFixtures(_app: unknown) {
     return { cleanup: async () => {} };
   }
   ```

### עדכון imports בתוך scaffolds

- API import path משתנה מ-`../../../qa-agent.app` ל-`../qa-agent.app` (file moved into `tests/qa-agent/`).
- כל body-author prompts מקבלים: "התייחס ל-`qa-agent.app` כמייצא את האפליקציה — אל תייצר ניסיונות לטעון את ה-app אחרת."

### קבצים שמשתנים / מתווספים

| קובץ | פעולה |
|---|---|
| [qa_agent/generators/harness.py](qa_agent/generators/harness.py) | **חדש** — emit_harness_files() עם 4 helpers (app shim, playwright config, vitest config, fixtures stub) |
| [qa_agent/scanners/api_scanner.py](qa_agent/scanners/api_scanner.py) | להוסיף `detect_app_entry(root, routes)` — מחזיר absolute path או None |
| [qa_agent/scanners/tech_stack.py](qa_agent/scanners/tech_stack.py) | אם vite.config.* קיים → קרא `server.port` (regex על שורה אחת); תוצאה נשמרת ב-`pm.dev_servers: dict` |
| [qa_agent/state/schemas.py](qa_agent/state/schemas.py) | `ProjectMap.dev_servers: dict[str, int]` (api/ui) |
| [qa_agent/cli/commands/scaffold.py](qa_agent/cli/commands/scaffold.py) | קורא ל-`emit_harness_files` בסוף phase |
| [qa_agent/generators/scaffolds.py](qa_agent/generators/scaffolds.py) | path הוא `../qa-agent.app` (לא `../../../qa-agent.app`); תיקון לכל ה-jest/vitest builders |
| [agents/qa-body-author.md](agents/qa-body-author.md) | להוסיף הוראה: אם תקלה ב-`import app` — אסור לעקוף; השאר `AUTHORING-GAP` |

### Acceptance

- אחרי scaffold: יש ארבעת הקבצים תחת `tests/qa-agent/` (כשהתנאים מתקיימים).
- ריצת בדיקה אחת `npx vitest run tests/qa-agent/api/auth.spec.ts` — module resolution לא נכשל; הטסט מגיע ל-assertions.
- ריצה ב-target עם `playwright.config.ts` כבר קיים: qa-agent **לא דורס**, משתמש ב-config הקיים.

---

## Fix I — Per-file log capture + structured failure context

### מה נשבר

`runs/<id>/logs/` ריקה. execution_history.json מציין מספרים בלבד. triage לא רואה לאיזה assertion הטסט נכשל ולא יכול לסווג `test-bug` vs `prod-bug` בלי context.

### מה צריך לקרות

1. **Per-file capture** ב-[qa_agent/executors/jest_runner.py](qa_agent/executors/jest_runner.py), [qa_agent/executors/playwright_runner.py](qa_agent/executors/playwright_runner.py), ובחדש [qa_agent/executors/vitest_runner.py](qa_agent/executors/vitest_runner.py):
   - הרצה עם reporter JSON: `--reporter=json --outputFile=<runs>/<id>/raw/<runner>.json` (jest/vitest) ; playwright: `--reporter=json`.
   - parse ה-JSON output; per-test, write `runs/<id>/logs/<test_id>.log` עם:
     - status
     - error message + stack trace
     - duration
     - file path
   - באם runner לא מצליח לעמוד ב-JSON reporter — fallback: capture stdout/stderr גלובלי לקובץ אחד `runs/<id>/logs/_combined.log`.

2. **Schema** ב-[qa_agent/state/schemas.py](qa_agent/state/schemas.py): `TestResult.error_excerpt: str` (אופציונלי) — הראשונים 2000 תווים של ה-stack/error. נשמר ב-`execution_history.json` per test.

3. **Triage prompt** ב-[agents/qa-triage.md](agents/qa-triage.md): להזכיר את ה-log path `state/runs/<id>/logs/<test_id>.log` כמקור ראשי לקריאה (במקום rerun).

### עקרונות

- אסור hardcoded reporter flags לפי runner-version — מבנים command-line `--reporter=json --outputFile=...`. אם flag לא תקף ב-runner ספציפי, ה-executor יחזיר `infra_error: reporter unsupported` ולא ינסה fallback רעוע.
- log captureי **אינו תלוי runner** — שכבת persistence אחת ב-`executors/base.py` שמייצרת קבצים לפי `test_id`. כל runner רק מספק `iter_results() -> list[ResultRecord]`.

### קבצים שמשתנים / מתווספים

| קובץ | פעולה |
|---|---|
| [qa_agent/executors/base.py](qa_agent/executors/base.py) | `persist_per_test_logs(run_dir, results)` — שכבת persistence משותפת |
| [qa_agent/executors/jest_runner.py](qa_agent/executors/jest_runner.py) | parse JSON reporter; קורא ל-`persist_per_test_logs` |
| [qa_agent/executors/playwright_runner.py](qa_agent/executors/playwright_runner.py) | אותו דבר |
| [qa_agent/executors/vitest_runner.py](qa_agent/executors/vitest_runner.py) | **חדש** — אותה תבנית כמו jest_runner, רק `vitest run --reporter=json` |
| [qa_agent/executors/a11y_runner.py](qa_agent/executors/a11y_runner.py) | אותו דבר (playwright reporter) |
| [qa_agent/executors/security_runner.py](qa_agent/executors/security_runner.py) | אותו דבר |
| [qa_agent/state/schemas.py](qa_agent/state/schemas.py) | `TestResult.error_excerpt: str = ""` |
| [agents/qa-triage.md](agents/qa-triage.md) | קריאה מ-`logs/<test_id>.log` במקום rerun |

### Acceptance

- אחרי run-tests: `runs/<id>/logs/<test_id>.log` קיים לכל test_id שהיה ב-execution_history.
- log טיפוסי מכיל: status (failed), error message, stack trace קצר.
- triage agent מסוגל להפיק verdict עם `confidence ≥ 0.75` ב-≥80% מהכשלים (vs 0% כיום).

---

## סדר ביצוע (v2)

| Step | Fix | תלות |
|---|---|---|
| 1 | G (runner detection + builders) | אין |
| 2 | H (harness emit) | G (כי harness לוקח בחשבון את ה-runner) |
| 3 | I (log capture) | אין; מקבילי ל-1+2 בעקרון |
| 4 | E2E re-run | G+H+I |

מומלץ: ביצוע סדרתי G → H → I, ואז ריצה מלאה אחת לוולידציה.

---

## Acceptance criteria מאוחדים

| # | בדיקה | יעד |
|---|---|---|
| 1 | scaffolds פולטים `from "vitest"` כש-target הוא vitest | ✓ |
| 2 | `tests/qa-agent/qa-agent.app.ts` קיים אחרי scaffold (אם app entry זוהה) | ✓ |
| 3 | `tests/qa-agent/playwright.config.ts` קיים (אם UI tests נוצרו ואין config ב-target) | ✓ |
| 4 | `tests/qa-agent/helpers/api-fixtures.ts` קיים | ✓ |
| 5 | ריצה ידנית של 1 בדיקת auth → module resolution success, assertions רצות | ✓ |
| 6 | `runs/<id>/logs/<test_id>.log` קיים לכל test_id שרץ | ✓ |
| 7 | run-tests מציג pass_rate > 0% (לא 0/332) | יעד מינימלי: > 10% (חלק מה-bodies יישארו תלויי-seed) |
| 8 | triage מצליח להחזיר verdict עם confidence על ≥80% מהכשלים | ✓ |
| 9 | דו"ח HTML סופי בעברית | ✓ (כבר נעשה) |

---

## עקרונות מחייבים — תזכורת

1. **אפס values project-specific.** detection דרך deps + config files; אסור list קבצים מ-`Candidate_Mngmnt`.
2. **אסור לדרוס קבצים קיימים.** check `if not file.exists()` לפני כל emit.
3. **Generic fallbacks בלבד.** vite default 5173, env var `QA_BASE_URL` עוקף.
4. **Namespace תחת `tests/qa-agent/`.** הקובץ היחיד בעל זכויות לחיות מחוץ הוא `qa-agent.app.ts` — וגם הוא הועבר תחת `tests/qa-agent/` ב-Fix H.
5. **Mental test לפני commit.** האם זה יעבוד על:
   - monorepo Vite+React+Express (Candidate_Mngmnt-style)
   - single-repo Next.js + Jest
   - Django + pytest
   - Vue + Vitest + Pinia

