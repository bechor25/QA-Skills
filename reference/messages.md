# Locale Messages

Reference for agents that need user-facing strings. Each agent picks the section matching `locale`.

## English

```
scan_start            : "Scanning {path}..."
scan_done             : "Found {N} files | {language} | {capabilities}"
state_check           : "Checking for changes since last run..."
state_summary         : "{N} files changed | {M} new | {K} unchanged"
state_no_change       : "No changes since last run."
state_no_prior        : "No prior run state — generating tests for all modules."
strategy_header       : "Execution plan (auto):"
strategy_starting     : "Starting..."
generating_tests      : "Generating tests..."
running_tests         : "Running tests and checking results..."
ui_skipped_no_server  : "UI tests skipped — server at {url} not reachable. Start the dev server and retry."
api_skipped_no_server : "API tests skipped — server at {url} not reachable."
flaky_running         : "Re-running suite to detect flaky tests..."
flaky_none            : "No flaky tests detected."
flaky_found           : "{N} flaky tests detected."
run_done              : "✅ Done. Quality score: {score}/100"
run_summary           : "   New: {new} | Updated: {updated} | Flaky: {flaky}"
run_recommendation    : "   {gaps} high-priority gaps — report opened in browser."
report_opened         : "📄 Report: {path}"
env_toolchain_missing : "Required tool not found: {tool}. Install it and retry."
install_playwright    : "Install Playwright first: npm install -D @playwright/test && npx playwright install"
install_axe           : "Install axe-core: npm install -D @axe-core/playwright"
resume_prompt         : "A previous run from {phase} is in progress. Resume?"
budget_exceeded       : "Token budget exceeded — returning partial results."
```

## Hebrew

```
scan_start            : "סורק את הפרויקט ב-{path}..."
scan_done             : "נמצאו {N} קבצים | {language} | {capabilities}"
state_check           : "בודק שינויים מהריצה הקודמת..."
state_summary         : "{N} קבצים השתנו | {M} קבצים חדשים | {K} ללא שינוי"
state_no_change       : "אין שינויים מהריצה הקודמת."
state_no_prior        : "אין ריצה קודמת — מייצר בדיקות לכל המודולים."
strategy_header       : "תוכנית ריצה (אוטומטית):"
strategy_starting     : "מתחיל..."
generating_tests      : "מייצר בדיקות..."
running_tests         : "מריץ בדיקות ובודק תוצאות..."
ui_skipped_no_server  : "בדיקות UI דולגו — השרת ב-{url} לא נגיש. הפעל את שרת הפיתוח ונסה שוב."
api_skipped_no_server : "בדיקות API דולגו — השרת ב-{url} לא נגיש."
flaky_running         : "מריץ את החבילה שוב לזיהוי בדיקות לא יציבות..."
flaky_none            : "לא זוהו בדיקות לא יציבות."
flaky_found           : "{N} בדיקות לא יציבות זוהו."
run_done              : "✅ הושלם. ציון איכות: {score}/100"
run_summary           : "   חדשות: {new} | עודכנו: {updated} | לא יציבות: {flaky}"
run_recommendation    : "   {gaps} פערים בעדיפות גבוהה — דוח פתוח בדפדפן."
report_opened         : "📄 הדוח: {path}"
env_toolchain_missing : "כלי הכרחי לא נמצא: {tool}. התקן ונסה שוב."
install_playwright    : "התקן Playwright: npm install -D @playwright/test && npx playwright install"
install_axe           : "התקן axe-core: npm install -D @axe-core/playwright"
resume_prompt         : "ריצה קודמת מ-{phase} בתהליך. להמשיך?"
budget_exceeded       : "תקציב הטוקנים חרג — מחזיר תוצאות חלקיות."
```
