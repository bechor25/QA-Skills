---
name: api-test
description: >
  Generate API/HTTP tests for REST endpoints, GraphQL, or any HTTP interface in the codebase.
  Covers: happy path, auth, schema validation, edge cases, error handling, CORS, pagination.
  Normally invoked by test-orchestrator as part of a full test run.
  Also usable standalone when the user asks to test APIs directly.

  English triggers (standalone): "test my API", "test the endpoints", "check auth flows",
  "validate API responses", "write API tests", "test my REST API", "test HTTP endpoints".

  Hebrew triggers (עברית): "בדוק את ה-API שלי", "בדיקות API", "בדוק את ה-endpoints שלי",
  "כתוב בדיקות API", "בדוק תשובות HTTP", "בדיקות REST", "בדוק נקודות קצה".

  Supports: httpx (Python), supertest (Node.js), RestAssured (Java), HttpClient (C#).
---

# api-test

Generates comprehensive HTTP-level tests for every route found by `code-analyzer`.

## Inputs

Receives from `test-orchestrator`:
```json
{
  "routes": [/* route objects from code-analyzer */],
  "modules": [/* controller/handler modules */],
  "project_root": "string",
  "language": "string",
  "run_type": "full | incremental"
}
```

## Output location

```
{project_root}/tests/api/{tag}.api.test.{ext}

Group by resource tag (inferred from route path):
  /auth/*      → tests/api/auth.api.test.ts
  /users/*     → tests/api/users.api.test.ts
  /products/*  → tests/api/products.api.test.ts
```

## For every endpoint — generate all of these

### 1. Happy path
```python
response = client.post("/auth/login", json={"email": "user@test.com", "password": "validPass1!"})
assert response.status_code == 200
assert "token" in response.json()
assert isinstance(response.json()["token"], str)
```

### 2. Authentication tests (for every protected route)

| Scenario | Expected |
|----------|----------|
| No `Authorization` header | 401 |
| `Authorization: Bearer invalid_token` | 401 |
| Expired token (use a known-expired JWT) | 401 |
| Valid token, wrong role/scope | 403 |
| Valid token, correct scope | 200/201/204 |

```python
EXPIRED_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.invalid"

def test_no_token_returns_401():
    r = client.get("/users/me")
    assert r.status_code == 401

def test_expired_token_returns_401():
    r = client.get("/users/me", headers={"Authorization": f"Bearer {EXPIRED_JWT}"})
    assert r.status_code == 401

def test_wrong_role_returns_403():
    r = client.delete("/admin/users/1", headers=user_auth_headers)
    assert r.status_code == 403
```

### 3. Schema validation — missing/wrong fields

```python
# Missing required field
r = client.post("/auth/login", json={"email": "user@test.com"})  # no password
assert r.status_code == 400 or r.status_code == 422
assert "password" in r.text.lower() or "required" in r.text.lower()

# Wrong type
r = client.post("/users", json={"age": "not-a-number"})
assert r.status_code == 400 or r.status_code == 422

# Extra unknown fields (check mass assignment protection)
r = client.post("/users", json={"email": "x@x.com", "role": "admin"})
assert r.status_code in (200, 201, 400, 422)
if r.status_code in (200, 201):
    assert r.json().get("role") != "admin"  # must not persist role from input
```

### 4. Edge cases

**Rate limiting** (if middleware detected):
```python
for _ in range(101):
    r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
assert r.status_code == 429
```

**Idempotency of PUT/PATCH**:
```python
r1 = client.put("/users/1", json={"name": "Alice"}, headers=auth)
r2 = client.put("/users/1", json={"name": "Alice"}, headers=auth)
assert r1.json() == r2.json()
```

**Empty body**:
```python
r = client.post("/users", data=b"", headers={"Content-Type": "application/json"})
assert r.status_code in (400, 422)
```

**Oversized payload** (>1MB):
```python
r = client.post("/users", json={"name": "x" * 1_000_001})
assert r.status_code in (400, 413)
```

### 5. Error response structure

Assert error body has a consistent shape — not just status code:
```python
r = client.post("/auth/login", json={"email": "bad"})
assert r.status_code in (400, 422)
body = r.json()
assert "error" in body or "message" in body or "errors" in body
# Must NOT contain stack trace
assert "at " not in r.text  # Node stack trace pattern
assert "Traceback" not in r.text  # Python traceback
assert "System.Exception" not in r.text  # .NET
```

### 6. Pagination (for list endpoints)
```python
r = client.get("/users?page=1&limit=10", headers=auth)
assert r.status_code == 200
assert isinstance(r.json()["items"], list)

# Last page
r = client.get("/users?page=9999&limit=10", headers=auth)
assert r.status_code == 200
assert r.json()["items"] == []

# Invalid page
r = client.get("/users?page=0", headers=auth)
assert r.status_code in (200, 400)

r = client.get("/users?page=-1", headers=auth)
assert r.status_code in (200, 400)
```

## What humans miss — mandatory inclusions

**GET endpoints must not mutate state**:
```python
def test_get_is_readonly():
    before = client.get("/users", headers=auth).json()
    client.get("/users/1", headers=auth)  # fetch one
    after = client.get("/users", headers=auth).json()
    assert before["total"] == after["total"]
```

**No sensitive data in error messages**:
```python
r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
assert "password" not in r.text.lower()
assert "hash" not in r.text.lower()
assert "salt" not in r.text.lower()
```

**CORS headers — only allowed origins get access**:
```python
r = client.options("/api/users", headers={"Origin": "https://evil.com"})
allowed = r.headers.get("Access-Control-Allow-Origin", "")
assert "evil.com" not in allowed

r = client.options("/api/users", headers={"Origin": "https://yourdomain.com"})
assert "yourdomain.com" in r.headers.get("Access-Control-Allow-Origin", "")
```

**Resource not found vs unauthorized — different status codes**:
```python
# Authenticated user, resource exists but belongs to other user
r = client.get("/users/OTHER_USER_ID/private", headers=own_auth)
assert r.status_code == 403  # NOT 200, NOT 404

# Non-existent resource
r = client.get("/users/99999999", headers=auth)
assert r.status_code == 404
```

**Numeric ID type handling**:
```python
r = client.get("/users/abc", headers=auth)  # string where int expected
assert r.status_code == 400 or r.status_code == 404
```

## Framework code templates

### Python (httpx + pytest)
```python
import pytest
import httpx

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="session")
def client():
    return httpx.Client(base_url=BASE_URL)

@pytest.fixture(scope="session")
def auth_headers(client):
    r = client.post("/auth/login", json={"email": "test@example.com", "password": "TestPass1!"})
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}
```

### TypeScript (supertest + Jest)
```typescript
import request from 'supertest';
import { app } from '../src/app';

describe('POST /auth/login', () => {
  let token: string;

  beforeAll(async () => {
    const r = await request(app).post('/auth/login')
      .send({ email: 'test@example.com', password: 'TestPass1!' });
    token = r.body.token;
  });

  it('returns 200 and token for valid credentials', async () => {
    const r = await request(app).post('/auth/login')
      .send({ email: 'test@example.com', password: 'TestPass1!' });
    expect(r.status).toBe(200);
    expect(r.body.token).toBeDefined();
  });
});
```

### Java (RestAssured)
```java
@ExtendWith(SpringExtension.class)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserApiTest {
    @LocalServerPort private int port;

    @BeforeEach
    void setUp() {
        RestAssured.baseURI = "http://localhost:" + port;
    }

    @Test
    void loginReturnsToken() {
        given()
            .contentType(ContentType.JSON)
            .body(Map.of("email", "test@example.com", "password", "TestPass1!"))
        .when()
            .post("/auth/login")
        .then()
            .statusCode(200)
            .body("token", notNullValue());
    }
}
```

### C# (HttpClient + NUnit)
```csharp
[TestFixture]
public class AuthApiTests
{
    private HttpClient _client;

    [OneTimeSetUp]
    public void Setup()
    {
        var factory = new WebApplicationFactory<Program>();
        _client = factory.CreateClient();
    }

    [Test]
    public async Task Login_ValidCredentials_Returns200WithToken()
    {
        var payload = JsonContent.Create(new { email = "test@example.com", password = "TestPass1!" });
        var response = await _client.PostAsync("/auth/login", payload);
        Assert.That(response.StatusCode, Is.EqualTo(HttpStatusCode.OK));
        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.That(body.GetProperty("token").GetString(), Is.Not.Empty);
    }
}
```

## Execute & fix loop

After writing test files, the orchestrator runs them and may return failures.
If failures reported:

1. Read failing test + source route file
2. Fix root cause: wrong status code expectation, wrong mock return type, wrong body key name
3. Fix **only** the failing test
4. Return updated file for re-run

Common API test failure causes:
- Expected 200 but route returns 201 (or vice versa)
- Mock returns `{ data: [...] }` but test expects `{ items: [...] }`
- Missing `Authorization` header in test request
- Supertest/httpx client not configured with base URL

Max 3 fix iterations. Mark `status: "partial"` if still failing.

## Output format (return to orchestrator)

```json
[
  {
    "source_module": "src/routes/auth.ts",
    "path": "tests/api/auth.api.test.ts",
    "tests_written": 14,
    "endpoints_covered": ["POST /auth/login", "POST /auth/refresh", "POST /auth/logout"],
    "status": "created | updated | partial",
    "execution_result": "passed | failed | not_run"
  }
]
```
