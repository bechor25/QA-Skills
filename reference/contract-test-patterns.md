# Contract Test Patterns

Reference loaded on demand by `qa-contract-test` agent.

## Mode openapi (TypeScript + ajv)

```typescript
import { test, expect } from '@playwright/test';
import Ajv from 'ajv';
import * as YAML from 'yaml';
import * as fs from 'fs';

const spec = YAML.parse(fs.readFileSync('openapi.yaml', 'utf-8'));
const ajv = new Ajv({ strict: false, allErrors: true });

function getResponseSchema(method: string, path: string, status: number) {
  const op = spec.paths[path]?.[method.toLowerCase()];
  return op?.responses?.[status]?.content?.['application/json']?.schema;
}

test('GET /users response matches OpenAPI schema', async ({ request }) => {
  const r = await request.get('/users', {
    headers: { Authorization: `Bearer ${process.env.TOKEN}` }
  });
  expect(r.status()).toBe(200);
  const body = await r.json();
  const schema = getResponseSchema('get', '/users', 200);
  const validate = ajv.compile(schema);
  if (!validate(body)) {
    console.log('Schema errors:', validate.errors);
    expect(validate.errors).toBeNull();
  }
});
```

## Mode openapi (Python + jsonschema)

```python
import yaml
import jsonschema
import httpx

with open("openapi.yaml") as f:
    spec = yaml.safe_load(f)

def get_response_schema(method, path, status):
    op = spec["paths"][path][method.lower()]
    return op["responses"][str(status)]["content"]["application/json"]["schema"]

def test_get_users_matches_schema():
    r = httpx.get("http://localhost:8000/users", headers={"Authorization": "Bearer ..."})
    assert r.status_code == 200
    schema = get_response_schema("get", "/users", 200)
    jsonschema.validate(r.json(), schema)
```

## Mode golden_capture (first run)

```python
import json, os, httpx

CONTRACTS_DIR = "contracts"
os.makedirs(CONTRACTS_DIR, exist_ok=True)

def capture(name, response_body):
    """Capture response shape (not values)."""
    shape = derive_shape(response_body)
    with open(f"{CONTRACTS_DIR}/{name}.json", "w") as f:
        json.dump(shape, f, indent=2)

def derive_shape(obj):
    if isinstance(obj, dict):
        return {k: derive_shape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [derive_shape(obj[0])] if obj else []
    return type(obj).__name__  # 'str', 'int', 'bool', etc.

def test_capture_users_list():
    r = httpx.get("http://localhost:8000/users", headers={"Authorization": "Bearer ..."})
    assert r.status_code == 200
    capture("users.list", r.json())
```

## Mode golden_update (subsequent runs)

```python
import json, httpx

def shapes_match(expected, actual):
    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(expected.keys()) != set(actual.keys()):
            return False, f"keys differ: expected {set(expected.keys())}, got {set(actual.keys())}"
        for k in expected:
            ok, reason = shapes_match(expected[k], actual[k])
            if not ok:
                return False, f"{k}: {reason}"
        return True, ""
    if isinstance(expected, list) and isinstance(actual, list):
        if not actual:
            return True, ""
        return shapes_match(expected[0], actual[0])
    if isinstance(expected, str) and not isinstance(actual, dict) and not isinstance(actual, list):
        return type(actual).__name__ == expected, f"type mismatch: expected {expected}, got {type(actual).__name__}"
    return True, ""

def test_users_list_shape_unchanged():
    with open("contracts/users.list.json") as f:
        expected = json.load(f)
    r = httpx.get("http://localhost:8000/users", headers={"Authorization": "Bearer ..."})
    assert r.status_code == 200
    ok, reason = shapes_match(expected, r.json())
    assert ok, f"contract drift: {reason}"
```

## Mode detection

```python
import os, glob

def detect_mode(project_root: str) -> str:
    candidates = [
        "openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json",
        "api/openapi.yaml", "docs/openapi.yaml", "src/openapi.yaml"
    ]
    for c in candidates:
        if os.path.exists(os.path.join(project_root, c)):
            return "openapi"
    contracts_dir = os.path.join(project_root, "contracts")
    if os.path.isdir(contracts_dir) and glob.glob(os.path.join(contracts_dir, "*.json")):
        return "golden_update"
    return "golden_capture"
```
