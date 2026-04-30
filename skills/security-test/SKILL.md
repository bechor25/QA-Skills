---
name: security-test
description: >
  Generate security-focused tests targeting OWASP Top 10 vulnerabilities found via static analysis.
  Covers: SQL injection, XSS, IDOR, privilege escalation, mass assignment, path traversal, timing attacks.
  No external security libraries required — pure HTTP client assertions.
  Normally invoked by test-orchestrator as part of a full test run.
  Also usable standalone when the user asks for security testing directly.

  English triggers (standalone): "security test", "check for vulnerabilities", "audit my auth",
  "test for injection", "OWASP", "penetration test", "find security issues", "security audit",
  "check for SQL injection", "test for XSS".

  Hebrew triggers (עברית): "בדיקות אבטחה", "בדוק חולשות", "ביקורת אבטחה",
  "בדוק הזרקת SQL", "בדוק XSS", "OWASP", "בדיקות חדירה", "מצא בעיות אבטחה",
  "בדוק הרשאות", "בדוק IDOR", "בדיקת אבטחת אימות".
---

# security-test

Generates security-focused tests targeting vulnerabilities found via static analysis of actual code.
No external tools required — pure HTTP client + assertions.

> **User-facing messages**: use `get_message(key, locale, **kwargs)` from
> `skills/_shared/validate.py`. Never hardcode strings the tester sees.

## Inputs

Receives from `test-orchestrator`:
```json
{
  "modules": [/* modules with has_auth, has_db_queries, input_fields from code-analyzer */],
  "routes": [/* all routes */],
  "warnings": [/* warnings from code-analyzer */],
  "project_root": "string",
  "language": "string"
}
```

## What to scan and when to activate each test category

| Code signal | Test category |
|-------------|--------------|
| `has_db_queries: true` | SQL/NoSQL injection |
| `input_fields` non-empty AND rendered in UI | XSS |
| `has_auth: true` | Auth & IDOR & privilege escalation |
| Any route returning user data | Sensitive data exposure |
| POST/PUT/PATCH endpoints | Mass assignment |
| File path parameters | Path traversal |
| Auth endpoints | Timing attacks |

Only generate tests for categories where signals are found. Do not generate generic tests.

## Output location

```
{project_root}/tests/security/{category}.security.test.{ext}

  tests/security/injection.security.test.py
  tests/security/auth.security.test.py
  tests/security/exposure.security.test.py
```

---

## A. SQL Injection (when `has_db_queries: true`)

```python
SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1' UNION SELECT null, null, null--",
    "' OR 1=1--",
    "admin'--",
    "1; SELECT sleep(5)--",  # time-based blind
    "' AND 1=CONVERT(int,(SELECT TOP 1 table_name FROM information_schema.tables))--",
]

@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_search(client, auth_headers, payload):
    """Endpoint must reject or sanitize SQL injection in query params."""
    r = client.get(f"/users/search?q={payload}", headers=auth_headers)
    
    # Must not return 200 with database dump content
    if r.status_code == 200:
        body = r.text.lower()
        assert "table_name" not in body
        assert "information_schema" not in body
        assert "syntax error" not in body  # raw DB errors = vuln
        assert "mysql" not in body
        assert "postgresql" not in body
    
    assert r.status_code != 500, "500 on injection payload suggests crash/vuln"

@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_login(client, payload):
    """Login endpoint must not authenticate via injection."""
    r = client.post("/auth/login", json={"email": payload, "password": payload})
    assert r.status_code in (400, 401, 422), \
        f"Login with injection payload returned {r.status_code} — possible bypass"
    assert "token" not in r.json(), "Token returned for injection payload — auth bypass!"
```

## B. NoSQL Injection (when DB patterns include MongoDB/Mongoose)

```python
NOSQL_PAYLOADS = [
    {"$gt": ""},          # always true operator
    {"$ne": None},        # not-equal bypass
    {"$regex": ".*"},     # regex match-all
    {"$where": "1==1"},   # JavaScript injection
]

def test_nosql_injection_in_login(client):
    for payload in NOSQL_PAYLOADS:
        r = client.post("/auth/login", json={"email": payload, "password": payload})
        assert r.status_code in (400, 401, 422), \
            f"NoSQL injection payload returned {r.status_code}"
        if r.status_code == 200:
            assert "token" not in r.json()
```

## C. XSS — Stored and Reflected (when `input_fields` non-empty)

```python
XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "javascript:alert(1)",
    "<svg onload=alert(1)>",
    "';alert(String.fromCharCode(88,83,83))//",
    "<iframe src=javascript:alert(1)>",
    "<<SCRIPT>alert('XSS');//<</SCRIPT>",
]

@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_input_is_escaped_in_response(client, auth_headers, payload):
    """Submitted XSS payload must never appear unescaped in any response."""
    # Store the payload
    r = client.post("/posts", json={"title": payload, "body": "normal content"}, 
                    headers=auth_headers)
    
    if r.status_code in (200, 201):
        post_id = r.json().get("id")
        
        # Retrieve and check it's escaped
        r2 = client.get(f"/posts/{post_id}", headers=auth_headers)
        body = r2.text
        
        # Raw script tags must not appear
        assert "<script>" not in body.lower(), \
            f"Unescaped <script> in response for payload: {payload}"
        assert "onerror=" not in body.lower(), \
            f"Unescaped event handler in response for payload: {payload}"
        assert "javascript:" not in body.lower(), \
            f"Unescaped javascript: protocol in response"

@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_in_query_param_reflected(client, payload):
    """Reflected XSS — payload in query param must not appear unescaped."""
    r = client.get(f"/search?q={payload}")
    assert "<script>" not in r.text.lower()
    assert "onerror=" not in r.text.lower()
```

## D. Authentication & Authorization

### IDOR (Insecure Direct Object Reference)
```python
def test_idor_cannot_access_other_user_resource(client, user_a_headers, user_b_id):
    """User A must not access User B's private resources."""
    r = client.get(f"/users/{user_b_id}/private-data", headers=user_a_headers)
    assert r.status_code in (403, 404), \
        f"IDOR: User A got {r.status_code} accessing User B's data"

def test_idor_cannot_modify_other_user_resource(client, user_a_headers, user_b_id):
    r = client.put(f"/users/{user_b_id}", 
                   json={"email": "hacked@attacker.com"},
                   headers=user_a_headers)
    assert r.status_code in (403, 404)

def test_idor_sequential_id_enumeration(client, auth_headers):
    """Try ID ±1 around authenticated user's ID — must not expose other users."""
    me = client.get("/users/me", headers=auth_headers).json()
    my_id = me["id"]
    
    for delta in [-1, 1]:
        r = client.get(f"/users/{my_id + delta}/private-data", headers=auth_headers)
        assert r.status_code in (403, 404), \
            f"IDOR: Got {r.status_code} for adjacent ID {my_id + delta}"
```

### Privilege Escalation
```python
def test_regular_user_cannot_reach_admin_endpoints(client, user_headers):
    """User-level token must be rejected by admin endpoints."""
    admin_endpoints = ["/admin/users", "/admin/settings", "/admin/logs"]
    for endpoint in admin_endpoints:
        r = client.get(endpoint, headers=user_headers)
        assert r.status_code in (403, 404), \
            f"Privilege escalation: user accessed {endpoint} with status {r.status_code}"

def test_token_scope_not_upgradeable(client, user_headers):
    """Cannot elevate own role via API."""
    r = client.patch("/users/me", json={"role": "admin"}, headers=user_headers)
    # Either 403 or request succeeds but role doesn't change
    if r.status_code in (200, 204):
        me = client.get("/users/me", headers=user_headers).json()
        assert me.get("role") != "admin", "User escalated own role to admin!"
```

## E. Sensitive Data Exposure

```python
def test_password_not_returned_in_user_response(client, auth_headers):
    r = client.get("/users/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    sensitive_keys = ["password", "passwordHash", "password_hash", "salt", "secret"]
    for key in sensitive_keys:
        assert key not in body, f"Sensitive field '{key}' exposed in /users/me response"

def test_tokens_not_exposed_in_list_response(client, auth_headers):
    r = client.get("/users", headers=auth_headers)
    for user in r.json().get("items", r.json() if isinstance(r.json(), list) else []):
        assert "token" not in user
        assert "password" not in user
        assert "secret" not in user

def test_error_response_has_no_stack_trace(client):
    """Trigger a server error — response must not contain stack traces."""
    # Send malformed request to trigger internal error
    r = client.post("/users", data="}{invalid json", 
                    headers={"Content-Type": "application/json"})
    if r.status_code >= 500:
        assert "Traceback" not in r.text       # Python
        assert "at Object." not in r.text      # Node.js
        assert "System.Exception" not in r.text  # .NET
        assert "java.lang." not in r.text      # Java

def test_internal_ips_not_leaked(client, auth_headers):
    r = client.get("/health", headers=auth_headers)
    for internal in ["10.0.", "192.168.", "172.16.", "127.0.0.1", "localhost"]:
        assert internal not in r.text
```

## F. Mass Assignment

```python
def test_mass_assignment_role_field_ignored(client):
    """Extra fields in POST body must not be persisted."""
    r = client.post("/users/register", json={
        "email": "mass@test.com",
        "password": "TestPass1!",
        "role": "admin",         # should be ignored
        "is_verified": True,     # should be ignored
        "credit_balance": 99999  # should be ignored
    })
    
    assert r.status_code in (200, 201)
    user = r.json()
    
    assert user.get("role") not in ("admin", "superuser"), "Mass assignment: role set from input"
    assert user.get("is_verified") is not True, "Mass assignment: is_verified set from input"
    assert user.get("credit_balance", 0) not in (99999,), "Mass assignment: credit set from input"

def test_mass_assignment_id_field_ignored(client, auth_headers):
    """Cannot set arbitrary ID via POST."""
    r = client.post("/posts", json={"title": "Test", "id": 99999}, headers=auth_headers)
    if r.status_code in (200, 201):
        assert r.json().get("id") != 99999, "Mass assignment: client-supplied ID accepted"
```

## G. Path Traversal (when file path params detected)

```python
PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..%2F..%2F..%2Fetc%2Fpasswd",
    "....//....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
]

@pytest.mark.parametrize("payload", PATH_TRAVERSAL_PAYLOADS)
def test_path_traversal_in_file_param(client, auth_headers, payload):
    r = client.get(f"/files/{payload}", headers=auth_headers)
    assert r.status_code in (400, 403, 404), \
        f"Path traversal: got {r.status_code} for payload '{payload}'"
    # Must not return file content
    assert "root:" not in r.text  # /etc/passwd content
    assert "[drivers]" not in r.text  # Windows hosts file
```

## H. Timing Attacks on Auth (when auth endpoints found)

```python
import time, statistics

def test_no_timing_difference_for_valid_vs_invalid_user(client):
    """Auth response time must not leak whether email exists."""
    ITERATIONS = 10
    
    existing_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        client.post("/auth/login", json={"email": "existing@test.com", "password": "wrong"})
        existing_times.append(time.perf_counter() - start)
    
    nonexistent_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        client.post("/auth/login", json={"email": "nobody@doesnotexist12345.com", "password": "wrong"})
        nonexistent_times.append(time.perf_counter() - start)
    
    avg_existing = statistics.mean(existing_times)
    avg_nonexistent = statistics.mean(nonexistent_times)
    
    # Allow max 100ms difference (network jitter tolerance)
    diff = abs(avg_existing - avg_nonexistent)
    assert diff < 0.1, \
        f"Timing leak: existing user avg {avg_existing*1000:.1f}ms vs " \
        f"nonexistent {avg_nonexistent*1000:.1f}ms (diff: {diff*1000:.1f}ms)"
```

## Additional "what testers miss" — Phase 8 additions

**JWT key confusion (RS256 → HS256 attack)**:
```python
import base64, json, hmac, hashlib

def test_jwt_rs256_hs256_confusion(client):
    """Critical: if server uses RS256, it must reject tokens signed with HS256 using the public key as secret."""
    # Craft a minimal HS256 token (attacker signs with server's public key as HMAC secret)
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "1", "role": "admin", "exp": 9999999999}).encode()).decode().rstrip("=")
    # Use "secret" as HMAC key (attacker doesn't know real secret — just testing alg confusion)
    sig_input = f"{header}.{payload}".encode()
    sig = base64.urlsafe_b64encode(hmac.new(b"secret", sig_input, hashlib.sha256).digest()).decode().rstrip("=")
    confused_token = f"{header}.{payload}.{sig}"

    r = client.get("/users/me", headers={"Authorization": f"Bearer {confused_token}"})
    assert r.status_code == 401, "JWT algorithm confusion: server accepted wrong-alg token!"
```

**Open redirect in callback/next params**:
```python
OPEN_REDIRECT_PAYLOADS = [
    "//evil.com", "https://evil.com", "//evil.com/%2f..", "///evil.com",
    "https:evil.com", "javascript:alert(1)"
]

@pytest.mark.parametrize("payload", OPEN_REDIRECT_PAYLOADS)
def test_no_open_redirect(client, payload):
    """?next= and ?return_to= must not redirect to external domains."""
    for param in ["next", "return_to", "redirect", "redirect_uri", "continue"]:
        r = client.get(f"/login?{param}={payload}", allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("Location", "")
            assert not location.startswith("//"), f"Open redirect via {param}: {location}"
            assert "evil.com" not in location, f"Open redirect via {param}: {location}"
```

**SSRF — Server-Side Request Forgery** (when URL-accepting field detected):
```python
SSRF_PAYLOADS = [
    "http://localhost:22", "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",  # AWS metadata
    "http://10.0.0.1/admin", "file:///etc/passwd",
]

@pytest.mark.parametrize("payload", SSRF_PAYLOADS)
def test_ssrf_url_param_rejected(client, auth_headers, payload):
    """URL parameters must not allow fetching internal addresses."""
    for url_param in ["url", "webhook", "callback", "image_url", "avatar"]:
        r = client.post("/settings", json={url_param: payload}, headers=auth_headers)
        # Must reject or ignore internal URLs
        assert r.status_code in (400, 422), \
            f"SSRF possible: {url_param}={payload} returned {r.status_code}"
```

## What humans miss — mandatory inclusions

**HTTP method override bypass**:
```python
def test_method_override_header_not_honored(client, user_headers):
    """_method=DELETE header must not bypass HTTP method restrictions."""
    r = client.post("/users/1", 
                    data={"_method": "DELETE"},
                    headers={**user_headers, "X-HTTP-Method-Override": "DELETE"})
    # Should not delete — method override must not work on sensitive ops
    assert r.status_code != 200, "HTTP method override allowed deletion via POST"
```

**JWT algorithm confusion**:
```python
def test_jwt_algorithm_confusion(client):
    """Server must reject tokens signed with 'none' algorithm."""
    # Craft a token with alg=none (unsigned)
    import base64, json
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "1", "role": "admin"}).encode()).decode().rstrip("=")
    none_token = f"{header}.{payload}."
    
    r = client.get("/users/me", headers={"Authorization": f"Bearer {none_token}"})
    assert r.status_code == 401, "JWT alg=none accepted — critical auth bypass!"
```

**CSRF — state-changing endpoints need CSRF protection or token-based auth**:
```python
def test_state_change_requires_origin_check(client, auth_headers):
    """POST from unexpected origin must be rejected or require CSRF token."""
    r = client.post("/users/me/delete-account",
                    headers={**auth_headers, "Origin": "https://evil.com"})
    assert r.status_code in (403, 401), \
        f"CSRF: state change from evil.com returned {r.status_code}"
```

## Execute & fix loop

After writing test files, the orchestrator runs them and may return failures.
If failures reported:

1. Read failing test + source module
2. Fix root cause: wrong auth mock structure, wrong SQL injection pattern, wrong status expectation
3. Fix **only** failing test — never weaken a security assertion to make a test pass
4. **Never** remove a security check because it fails — if the app doesn't prevent an attack, mark `vulnerabilities_found` and leave test as-is
5. Return updated file for re-run

Security test fail reasons to fix (test bug, not app bug):
- Mock middleware setup incorrect — token header format mismatch
- `describe.each` payload list syntax error
- Wrong import path for app

Security test fails that indicate real vulnerabilities (do NOT fix test):
- SQL error leaks in response body
- 200 returned for injection payload
- `passwordHash` present in response
- Stack trace in error body

Max 3 fix iterations. Mark `status: "partial"` if still failing after app-side fixes only.

## Output format (return to orchestrator)

```json
[
  {
    "source_module": "src/auth/login.ts",
    "path": "tests/security/auth.security.test.py",
    "tests_written": 11,
    "assertions_covered": ["jwt:alg_none_rejected", "jwt:tampered_payload", "sql_injection:login_email", "idor:update_other_user"],
    "categories_covered": ["auth", "idor", "timing", "privilege-escalation"],
    "vulnerabilities_found": [],
    "status": "created | updated | partial",
    "execution_result": "passed | failed | not_run"
  }
]
```

`assertions_covered` is the canonical field used by the orchestrator for deduplication.
Format: `"{category}:{test_scenario}"`. Include one entry per test case generated.
`categories_covered` is kept for backward compatibility.

Note: `vulnerabilities_found` is populated only if tests detect actual vulnerabilities
during generation (e.g., if code-analyzer warnings indicate a clear pattern).
Leave empty otherwise — test execution confirms presence, not static analysis.
