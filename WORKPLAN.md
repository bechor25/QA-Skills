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
