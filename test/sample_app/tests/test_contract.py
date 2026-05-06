"""Contract tests — verify the OpenAPI schema matches actual API behavior."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.users import store


@pytest.fixture(autouse=True)
def reset_store():
    store._users.clear()
    store._next_id = 1
    yield
    store._users.clear()
    store._next_id = 1


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def openapi_schema(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Schema structure
# ---------------------------------------------------------------------------

class TestOpenAPIStructure:
    def test_openapi_version_present(self, openapi_schema):
        assert "openapi" in openapi_schema
        assert openapi_schema["openapi"].startswith("3.")

    def test_info_block(self, openapi_schema):
        info = openapi_schema.get("info", {})
        assert info.get("title") == "Sample QA App"
        assert "version" in info

    def test_paths_non_empty(self, openapi_schema):
        paths = openapi_schema.get("paths", {})
        assert len(paths) > 0

    def test_components_schemas_present(self, openapi_schema):
        assert "components" in openapi_schema
        schemas = openapi_schema["components"].get("schemas", {})
        assert len(schemas) > 0


# ---------------------------------------------------------------------------
# Route existence in schema
# ---------------------------------------------------------------------------

class TestRoutePresence:
    @pytest.mark.parametrize("path,method", [
        ("/api/register", "post"),
        ("/api/login", "post"),
        ("/api/me", "get"),
        ("/api/users", "get"),
        ("/api/users/{user_id}", "get"),
        ("/api/calc/quote", "post"),
        ("/api/health", "get"),
    ])
    def test_route_in_schema(self, openapi_schema, path, method):
        paths = openapi_schema.get("paths", {})
        assert path in paths, f"Expected path {path} in OpenAPI schema"
        assert method in paths[path], f"Expected method {method} for path {path}"


# ---------------------------------------------------------------------------
# Schema matches actual responses
# ---------------------------------------------------------------------------

class TestResponseSchemaCompliance:
    def test_health_response_matches_schema(self, client, openapi_schema):
        """GET /api/health returns {"status": "ok"} as documented."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body

    def test_register_response_matches_schema(self, client, openapi_schema):
        """POST /api/register returns UserResp shape."""
        resp = client.post("/api/register", json={
            "email": "contract@test.com",
            "name": "Contract User",
            "password": "contractpass"
        })
        assert resp.status_code == 201
        body = resp.json()
        # Must have all UserResp fields
        for field in ["id", "email", "name", "role"]:
            assert field in body, f"UserResp missing field: {field}"

    def test_login_response_matches_schema(self, client, openapi_schema):
        """POST /api/login returns TokenResp shape."""
        store.create("login@test.com", "Login", "loginpass1")
        resp = client.post("/api/login", json={"email": "login@test.com", "password": "loginpass1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "token_type" in body
        assert body["token_type"] == "bearer"

    def test_calc_quote_response_matches_schema(self, client, openapi_schema):
        """POST /api/calc/quote returns CalcResp shape."""
        resp = client.post("/api/calc/quote", json={"price": 100.0})
        assert resp.status_code == 200
        body = resp.json()
        for field in ["discounted", "tax", "total"]:
            assert field in body, f"CalcResp missing field: {field}"
        assert all(isinstance(body[f], float) for f in ["discounted", "tax", "total"])


# ---------------------------------------------------------------------------
# Error response contracts
# ---------------------------------------------------------------------------

class TestErrorResponseContracts:
    def test_422_has_detail(self, client):
        """Validation errors must return detail array per FastAPI/OpenAPI standard."""
        resp = client.post("/api/register", json={"email": "bad"})
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)

    def test_401_structure(self, client):
        """Unauthorized responses must include detail."""
        resp = client.get("/api/me")
        assert resp.status_code == 401
        body = resp.json()
        assert "detail" in body

    def test_409_on_duplicate_register(self, client):
        """Duplicate registration returns 409 Conflict."""
        payload = {"email": "dup@test.com", "name": "Dup", "password": "duppassword"}
        client.post("/api/register", json=payload)
        resp = client.post("/api/register", json=payload)
        assert resp.status_code == 409

    def test_404_on_missing_user(self, client):
        """Requesting nonexistent user returns 404."""
        store.create("admin@test.com", "Admin", "adminpass1", role="admin")
        login_resp = client.post("/api/login", json={"email": "admin@test.com", "password": "adminpass1"})
        token = login_resp.json()["access_token"]
        resp = client.get("/api/users/99999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Schema field types
# ---------------------------------------------------------------------------

class TestSchemaFieldTypes:
    def test_user_id_is_integer(self, client):
        """User.id must be an integer, not a string."""
        resp = client.post("/api/register", json={
            "email": "typechk@test.com",
            "name": "TypeCheck",
            "password": "typechkpass"
        })
        assert resp.status_code == 201
        assert isinstance(resp.json()["id"], int)

    def test_token_is_string(self, client):
        """access_token must be a string."""
        store.create("tok@test.com", "Tok", "tokpassword")
        resp = client.post("/api/login", json={"email": "tok@test.com", "password": "tokpassword"})
        assert isinstance(resp.json()["access_token"], str)

    def test_calc_fields_are_floats(self, client):
        """CalcResp fields must be numeric (float/int)."""
        resp = client.post("/api/calc/quote", json={"price": 50.0})
        body = resp.json()
        assert isinstance(body["discounted"], (int, float))
        assert isinstance(body["tax"], (int, float))
        assert isinstance(body["total"], (int, float))
