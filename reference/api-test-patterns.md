# API Test Patterns

Reference loaded on demand by `qa-api-test` agent. Read only the section needed.

## Python / httpx + pytest

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

EXPIRED_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.invalid"

def test_login_happy(client):
    r = client.post("/auth/login", json={"email": "test@example.com", "password": "TestPass1!"})
    assert r.status_code == 200
    assert "token" in r.json()

def test_no_token_returns_401(client):
    r = client.get("/users/me")
    assert r.status_code == 401

def test_expired_token(client):
    r = client.get("/users/me", headers={"Authorization": f"Bearer {EXPIRED_JWT}"})
    assert r.status_code == 401

def test_missing_required_field(client):
    r = client.post("/auth/login", json={"email": "x@x.com"})
    assert r.status_code in (400, 422)

def test_extra_field_ignored(client, auth_headers):
    r = client.post("/users", json={"email": "u@x.com", "role": "admin"}, headers=auth_headers)
    if r.status_code in (200, 201):
        assert r.json().get("role") != "admin"

def test_pagination(client, auth_headers):
    r = client.get("/users?page=1&limit=10", headers=auth_headers)
    assert r.status_code == 200
    r = client.get("/users?page=9999&limit=10", headers=auth_headers)
    assert r.status_code == 200

def test_no_stack_trace_in_error(client):
    r = client.post("/users", data="}{invalid", headers={"Content-Type": "application/json"})
    assert "Traceback" not in r.text
    assert "at Object." not in r.text

def test_get_is_readonly(client, auth_headers):
    before = client.get("/users", headers=auth_headers).json()
    client.get("/users/1", headers=auth_headers)
    after = client.get("/users", headers=auth_headers).json()
    assert before == after

def test_403_for_other_user(client, own_auth):
    r = client.get("/users/OTHER_USER_ID/private", headers=own_auth)
    assert r.status_code == 403
```

## TypeScript / supertest + Jest

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

  it('returns 200 + token', async () => {
    const r = await request(app).post('/auth/login')
      .send({ email: 'test@example.com', password: 'TestPass1!' });
    expect(r.status).toBe(200);
    expect(r.body.token).toBeDefined();
  });

  it('400 on missing password', async () => {
    const r = await request(app).post('/auth/login').send({ email: 'x@x.com' });
    expect([400, 422]).toContain(r.status);
  });

  it('401 without token', async () => {
    const r = await request(app).get('/users/me');
    expect(r.status).toBe(401);
  });

  it('403 for other user resource', async () => {
    const r = await request(app)
      .get('/users/OTHER_ID/private')
      .set('Authorization', `Bearer ${token}`);
    expect(r.status).toBe(403);
  });

  it('CORS rejects evil origin', async () => {
    const r = await request(app).options('/api/users').set('Origin', 'https://evil.com');
    expect(r.headers['access-control-allow-origin'] || '').not.toContain('evil.com');
  });
});
```

## Coverage checklist (per endpoint)

- Happy path (status + body shape)
- Auth: no token / invalid / expired / wrong scope / valid scope
- Schema: missing required / wrong type / extra fields not persisted
- Edge: rate limit, idempotent PUT, empty body, oversized payload
- Error shape: has `error`/`message` key, no stack traces
- Pagination: page=1, page=9999, page=-1
- Auth matrix: every role × every protected route
- Trailing slash: `/x` and `/x/`
- Concurrent writes: no 500
- GET is readonly
- No sensitive data in errors
- CORS rejects evil origin
- 403 vs 404 distinction
- Numeric ID validation (`/users/abc`)
