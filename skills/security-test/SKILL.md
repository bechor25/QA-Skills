---
name: security-test
description: >
  Generate security-focused tests targeting OWASP Top 10. Standalone entry point —
  delegates to qa-security-test agent.

  English triggers (standalone): "security test", "check for vulnerabilities", "audit my auth",
  "test for injection", "OWASP", "penetration test", "find security issues", "security audit",
  "check for SQL injection", "test for XSS".

  Hebrew triggers (עברית): "בדיקות אבטחה", "בדוק חולשות", "ביקורת אבטחה",
  "בדוק הזרקת SQL", "בדוק XSS", "OWASP", "בדיקות חדירה", "מצא בעיות אבטחה",
  "בדוק הרשאות", "בדוק IDOR", "בדיקת אבטחת אימות".
---

# security-test (entry point)

Thin trigger skill. Delegates to `qa-skills:qa-security-test` agent.

## Behavior

1. Detect locale.
2. Resolve `project_root`.
3. Invoke `qa-skills:qa-code-analyzer` to get modules + routes + warnings.
4. Detect API server URL.
5. Invoke `qa-skills:qa-security-test` agent with:
   ```json
   {
     "project_root": "...",
     "language": "...",
     "modules": [...],
     "routes": [...],
     "warnings": [...],
     "locale": "he|en",
     "preflight": {"server_check_url": "<detected>", "abort_if_no_server": true},
     "budgets": {"max_tokens": 80000, "max_seconds": 600}
   }
   ```
6. Display agent summary including any `vulnerabilities_found`.

The agent owns OWASP test generation and never weakens security assertions.
