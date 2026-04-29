---
name: contract-test
description: >
  Generate contract tests that verify API responses match their declared schema (OpenAPI/Swagger)
  or a golden-master captured on first run. Catches unintentional API drift before it breaks consumers.
  Normally invoked by test-orchestrator when routes are detected.
  Also usable standalone when user asks for contract or schema testing.

  English triggers (standalone): "contract test", "OpenAPI test", "schema test", "API schema validation",
  "check if API matches spec", "validate API contract", "test schema conformance".

  Hebrew triggers (עברית): "בדיקות חוזה", "בדיקות OpenAPI", "בדיקות schema", "בדוק ה-API מול המפרט",
  "אמת את החוזה", "בדיקות schema validation", "בדוק סכמת תגובות".
---

# contract-test

Generates tests asserting API responses conform to declared or captured schemas.

## Inputs

Receives `RunContext`. Key fields:
- `analysis.routes`
- `project_root`
- `language`
- `user_locale`

## Output location

```
{project_root}/tests/contract/{tag}.contract.test.{ext}
{project_root}/contracts/{route_tag}.json   ← golden masters (golden mode only)
```

---

## Mode detection

```python
import os, glob

def detect_mode(project_root: str) -> str:
    # Check for OpenAPI spec
    candidates = [
        "openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json",
        "api/openapi.yaml", "docs/openapi.yaml", "src/openapi.yaml"
    ]
    for c in candidates:
        if os.path.exists(os.path.join(project_root, c)):
            return "openapi"
    # Check if golden masters exist from prior run
    contracts_dir = os.path.join(project_root, "contracts")
    if os.path.isdir(contracts_dir) and glob.glob(os.path.join(contracts_dir, "*.json")):
        return "golden_update"
    return "golden_capture"
```

---

## Mode A — OpenAPI present

### Parse the spec

```python
import yaml, json

def load_openapi(project_root: str) -> dict:
    for name in ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"]:
        path = os.path.join(project_root, name)
        if os.path.exists(path):
            with open(path) as f:
                return yaml.safe_load(f) if name.endswith(".yaml") else json.load(f)
    return {}
```

Extract per-route response schemas. For each route in `analysis.routes`:
1. Look up route in OpenAPI `paths`.
2. Extract response schema for each status code.
3. Generate test asserting response matches schema.

### Generated test (Python — httpx + pytest + jsonschema)

```python
import pytest, httpx, jsonschema, json

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="session")
def client():
    return httpx.Client(base_url=BASE_URL)

@pytest.fixture(scope="session")
def auth_token(client):
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
    return r.json().get("token", "")

# Schema loaded from openapi.yaml
LOGIN_200_SCHEMA = {
    "type": "object",
    "required": ["token"],
    "properties": {"token": {"type": "string"}}
}

class TestAuthLoginContract:
    def test_200_matches_schema(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        assert r.status_code == 200
        jsonschema.validate(r.json(), LOGIN_200_SCHEMA)

    def test_401_response_is_json(self, client):
        r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
        assert r.status_code == 401
        # Must return JSON, not HTML error page
        assert r.headers.get("content-type", "").startswith("application/json")

    def test_no_extra_sensitive_fields(self, client, auth_token):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        body = r.json()
        forbidden = ["password", "passwordHash", "password_hash", "salt"]
        for field in forbidden:
            assert field not in body, f"Sensitive field '{field}' exposed in login response"
```

### Generated test (TypeScript — supertest + Jest + ajv)

```typescript
import request from 'supertest';
import { app } from '../src/app';
import Ajv from 'ajv';

const ajv = new Ajv();

const LOGIN_200_SCHEMA = {
  type: 'object',
  required: ['token'],
  properties: { token: { type: 'string' } },
  additionalProperties: true,
};

describe('Contract: POST /auth/login', () => {
  it('200 response matches declared schema', async () => {
    const r = await request(app)
      .post('/auth/login')
      .send({ email: 'user@test.com', password: 'TestPass1!' });
    expect(r.status).toBe(200);
    const valid = ajv.validate(LOGIN_200_SCHEMA, r.body);
    expect(valid, ajv.errorsText()).toBe(true);
  });

  it('no additional undeclared required fields missing', async () => {
    const r = await request(app)
      .post('/auth/login')
      .send({ email: 'user@test.com', password: 'TestPass1!' });
    // Every field declared as required in schema must be present
    expect(r.body.token).toBeDefined();
  });
});
```

---

## Mode B — Golden master (no OpenAPI)

### Capture phase (first run)

```python
import json, os, hashlib, datetime

def capture_golden(client, routes: list, contracts_dir: str):
    os.makedirs(contracts_dir, exist_ok=True)
    for route in routes:
        try:
            if route["method"] == "GET":
                r = make_request(client, route, auth=True)
            elif route["method"] == "POST":
                r = make_request(client, route, auth=False, body={})
            else:
                continue

            if r.status_code < 500:
                master = {
                    "route": f"{route['method']} {route['path']}",
                    "captured_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "status_code": r.status_code,
                    "schema": infer_schema(r.json() if r.headers.get('content-type','').startswith('application/json') else {})
                }
                slug = route["path"].strip("/").replace("/", "_") or "root"
                path = os.path.join(contracts_dir, f"{route['method'].lower()}_{slug}.json")
                with open(path, "w") as f:
                    json.dump(master, f, indent=2)
        except Exception:
            pass  # Skip routes that fail to respond
```

### Schema inference

```python
def infer_schema(data, depth=0) -> dict:
    if depth > 5:
        return {}
    if isinstance(data, dict):
        return {
            "type": "object",
            "properties": {k: infer_schema(v, depth+1) for k, v in data.items()},
            "required": list(data.keys())
        }
    elif isinstance(data, list):
        return {"type": "array", "items": infer_schema(data[0], depth+1) if data else {}}
    elif isinstance(data, bool):
        return {"type": "boolean"}
    elif isinstance(data, int):
        return {"type": "integer"}
    elif isinstance(data, float):
        return {"type": "number"}
    elif isinstance(data, str):
        return {"type": "string"}
    else:
        return {}
```

### Comparison phase (subsequent runs)

Generate a test that loads the golden master and compares live response schema:

```python
def test_login_response_matches_contract(client):
    golden_path = "contracts/post_auth_login.json"
    with open(golden_path) as f:
        master = json.load(f)

    r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
    assert r.status_code == master["status_code"], \
        f"Status changed from {master['status_code']} to {r.status_code}"

    live_schema = infer_schema(r.json())
    schema_drift = find_schema_drift(master["schema"], live_schema)

    if schema_drift:
        # Never fail silently — print human message
        print(get_message("contract_changed", locale, route=route_path))
        raise AssertionError(f"Contract drift detected:\n{json.dumps(schema_drift, indent=2)}")
```

```python
def find_schema_drift(expected: dict, actual: dict, path="root") -> list:
    drifts = []
    if expected.get("type") != actual.get("type"):
        drifts.append(f"{path}: type changed from '{expected.get('type')}' to '{actual.get('type')}'")
    if expected.get("type") == "object":
        for key in expected.get("required", []):
            if key not in actual.get("properties", {}):
                drifts.append(f"{path}.{key}: required field removed")
    return drifts
```

---

## What humans miss — mandatory inclusions

**Content-Type header is always application/json**:
```python
def test_content_type_is_json(client, auth_token):
    r = client.get("/users", headers={"Authorization": f"Bearer {auth_token}"})
    assert "application/json" in r.headers.get("content-type", ""), \
        "Response Content-Type is not application/json"
```

**No undocumented fields in error responses**:
```python
def test_error_response_has_standard_shape(client):
    r = client.post("/auth/login", json={"email": "bad"})
    body = r.json()
    # Error shape must be stable: {error: string} or {message: string} or {errors: [...]}
    has_error_field = "error" in body or "message" in body or "errors" in body
    assert has_error_field, f"Non-standard error response shape: {list(body.keys())}"
```

**Arrays never return nulls**:
```python
def test_list_items_are_not_null(client, auth_token):
    r = client.get("/users", headers={"Authorization": f"Bearer {auth_token}"})
    items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
    for item in items:
        assert item is not None, "List contains null item"
```

---

## Execute & fix loop

Run: `pytest tests/contract/ -q 2>&1` / `npx jest tests/contract/ 2>&1`

If failure is `contract_changed` (schema drift): do NOT fix the test — print `contract_changed` message to user.
If failure is a test infrastructure issue (wrong import, wrong base URL): fix it.

Max 3 fix iterations.

---

## Output format (return to orchestrator)

```json
[
  {
    "source_module": "src/routes/auth.ts",
    "path": "tests/contract/auth.contract.test.ts",
    "tests_written": 6,
    "mode": "openapi | golden_capture | golden_update",
    "routes_covered": ["POST /auth/login", "GET /users"],
    "contract_drift_detected": false,
    "assertions_covered": ["auth.login.schema", "auth.login.no_sensitive_fields"],
    "status": "created | updated | partial",
    "execution_result": "passed | failed | not_run"
  }
]
```
