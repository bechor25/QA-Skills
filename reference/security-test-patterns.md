# Security Test Patterns (OWASP)

Reference loaded on demand by `qa-security-test` agent. Read only the section needed.

## Payload arrays

```python
SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1' UNION SELECT null, null, null--",
    "' OR 1=1--",
    "admin'--",
    "1; SELECT sleep(5)--",
    "' AND 1=CONVERT(int,(SELECT TOP 1 table_name FROM information_schema.tables))--",
]

NOSQL_PAYLOADS = [
    {"$gt": ""}, {"$ne": None}, {"$regex": ".*"}, {"$where": "1==1"},
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "javascript:alert(1)",
    "<svg onload=alert(1)>",
    "';alert(String.fromCharCode(88,83,83))//",
    "<iframe src=javascript:alert(1)>",
]

PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..%2F..%2F..%2Fetc%2Fpasswd",
    "....//....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
]

SSRF_PAYLOADS = [
    "http://localhost:22",
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/admin",
    "file:///etc/passwd",
]

OPEN_REDIRECT_PAYLOADS = [
    "//evil.com", "https://evil.com", "//evil.com/%2f..", "///evil.com",
    "https:evil.com", "javascript:alert(1)",
]
```

## SQL Injection (httpx + pytest)

```python
@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sqli_search(client, auth_headers, payload):
    r = client.get(f"/users/search?q={payload}", headers=auth_headers)
    if r.status_code == 200:
        body = r.text.lower()
        assert "table_name" not in body
        assert "information_schema" not in body
        assert "syntax error" not in body
        assert "mysql" not in body
        assert "postgresql" not in body
    assert r.status_code != 500

@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sqli_login(client, payload):
    r = client.post("/auth/login", json={"email": payload, "password": payload})
    assert r.status_code in (400, 401, 422)
    assert "token" not in r.text.lower()
```

## XSS

```python
@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_stored(client, auth_headers, payload):
    r = client.post("/posts", json={"title": payload, "body": "x"}, headers=auth_headers)
    if r.status_code in (200, 201):
        post_id = r.json().get("id")
        r2 = client.get(f"/posts/{post_id}", headers=auth_headers)
        body = r2.text.lower()
        assert "<script>" not in body
        assert "onerror=" not in body
        assert "javascript:" not in body
```

## IDOR

```python
def test_idor_other_user(client, user_a_headers, user_b_id):
    r = client.get(f"/users/{user_b_id}/private-data", headers=user_a_headers)
    assert r.status_code in (403, 404)

def test_idor_id_enumeration(client, auth_headers):
    me = client.get("/users/me", headers=auth_headers).json()
    for delta in [-1, 1]:
        r = client.get(f"/users/{me['id'] + delta}/private", headers=auth_headers)
        assert r.status_code in (403, 404)
```

## Privilege escalation

```python
def test_user_cannot_admin(client, user_headers):
    for ep in ["/admin/users", "/admin/settings"]:
        r = client.get(ep, headers=user_headers)
        assert r.status_code in (403, 404)

def test_role_not_upgradeable(client, user_headers):
    r = client.patch("/users/me", json={"role": "admin"}, headers=user_headers)
    me = client.get("/users/me", headers=user_headers).json()
    assert me.get("role") != "admin"
```

## Sensitive data exposure

```python
def test_no_password_in_response(client, auth_headers):
    r = client.get("/users/me", headers=auth_headers)
    body = r.json()
    for key in ["password", "passwordHash", "password_hash", "salt", "secret"]:
        assert key not in body

def test_no_stack_trace(client):
    r = client.post("/users", data="}{invalid", headers={"Content-Type": "application/json"})
    if r.status_code >= 500:
        assert "Traceback" not in r.text
        assert "at Object." not in r.text
        assert "System.Exception" not in r.text
        assert "java.lang." not in r.text
```

## Mass assignment

```python
def test_role_field_ignored(client):
    r = client.post("/users/register", json={
        "email": "m@t.com", "password": "Pass1!",
        "role": "admin", "is_verified": True, "credit_balance": 99999
    })
    if r.status_code in (200, 201):
        u = r.json()
        assert u.get("role") not in ("admin", "superuser")
        assert u.get("is_verified") is not True
        assert u.get("credit_balance", 0) != 99999
```

## Path traversal

```python
@pytest.mark.parametrize("payload", PATH_TRAVERSAL_PAYLOADS)
def test_path_traversal(client, auth_headers, payload):
    r = client.get(f"/files/{payload}", headers=auth_headers)
    assert r.status_code in (400, 403, 404)
    assert "root:" not in r.text
    assert "[drivers]" not in r.text
```

## JWT alg=none

```python
def test_jwt_alg_none_rejected(client):
    import base64, json
    h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"sub": "1", "role": "admin"}).encode()).decode().rstrip("=")
    none_token = f"{h}.{p}."
    r = client.get("/users/me", headers={"Authorization": f"Bearer {none_token}"})
    assert r.status_code == 401
```

## JWT RS256 → HS256 confusion

```python
def test_jwt_alg_confusion(client):
    import base64, json, hmac, hashlib
    h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"sub": "1", "role": "admin", "exp": 9999999999}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(b"secret", f"{h}.{p}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    confused = f"{h}.{p}.{sig}"
    r = client.get("/users/me", headers={"Authorization": f"Bearer {confused}"})
    assert r.status_code == 401
```

## Open redirect

```python
@pytest.mark.parametrize("payload", OPEN_REDIRECT_PAYLOADS)
def test_no_open_redirect(client, payload):
    for param in ["next", "return_to", "redirect", "redirect_uri"]:
        r = client.get(f"/login?{param}={payload}", follow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            assert not loc.startswith("//")
            assert "evil.com" not in loc
```

## SSRF

```python
@pytest.mark.parametrize("payload", SSRF_PAYLOADS)
def test_ssrf_blocked(client, auth_headers, payload):
    for url_param in ["url", "webhook", "callback", "image_url"]:
        r = client.post("/settings", json={url_param: payload}, headers=auth_headers)
        assert r.status_code in (400, 422)
```

## Timing attack

```python
import time, statistics

def test_login_timing(client):
    N = 10
    existing = []
    for _ in range(N):
        s = time.perf_counter()
        client.post("/auth/login", json={"email": "existing@t.com", "password": "wrong"})
        existing.append(time.perf_counter() - s)
    nonexistent = []
    for _ in range(N):
        s = time.perf_counter()
        client.post("/auth/login", json={"email": "nobody@nothere12345.com", "password": "wrong"})
        nonexistent.append(time.perf_counter() - s)
    diff = abs(statistics.mean(existing) - statistics.mean(nonexistent))
    assert diff < 0.1
```

## CSRF / Origin check

```python
def test_csrf_evil_origin_rejected(client, auth_headers):
    r = client.post("/users/me/delete-account",
                    headers={**auth_headers, "Origin": "https://evil.com"})
    assert r.status_code in (403, 401)
```
