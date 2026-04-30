import pytest
import json
from fastapi.testclient import TestClient

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from main import app
from src.users import users_store


def infer_schema(data, depth=0) -> dict:
    if depth > 5:
        return {}
    if isinstance(data, dict):
        return {
            "type": "object",
            "properties": {k: infer_schema(v, depth + 1) for k, v in data.items()},
            "required": list(data.keys()),
        }
    elif isinstance(data, list):
        return {"type": "array", "items": infer_schema(data[0], depth + 1) if data else {}}
    elif isinstance(data, bool):
        return {"type": "boolean"}
    elif isinstance(data, int):
        return {"type": "integer"}
    elif isinstance(data, float):
        return {"type": "number"}
    elif isinstance(data, str):
        return {"type": "string"}
    return {}


def find_schema_drift(expected: dict, actual: dict, path="root") -> list:
    drifts = []
    if expected.get("type") != actual.get("type"):
        drifts.append(f"{path}: type changed from '{expected.get('type')}' to '{actual.get('type')}'")
    if expected.get("type") == "object":
        for key in expected.get("required", []):
            if key not in actual.get("properties", {}):
                drifts.append(f"{path}.{key}: required field removed from response")
    return drifts


# Hard-coded golden schemas derived from current implementation
LOGIN_200_SCHEMA = {
    "type": "object",
    "required": ["token", "user_id"],
    "properties": {
        "token": {"type": "string"},
        "user_id": {"type": "integer"},
    },
}

ME_200_SCHEMA = {
    "type": "object",
    "required": ["user_id", "role"],
    "properties": {
        "user_id": {"type": "string"},
        "role": {"type": "string"},
    },
}

USERS_LIST_200_SCHEMA = {
    "type": "object",
    "required": ["items", "total"],
    "properties": {
        "items": {"type": "array"},
        "total": {"type": "integer"},
    },
}

USER_OBJECT_SCHEMA = {
    "type": "object",
    "required": ["id", "email", "name", "role"],
    "properties": {
        "id": {"type": "integer"},
        "email": {"type": "string"},
        "name": {"type": "string"},
        "role": {"type": "string"},
    },
}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def user_token(client):
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/auth/login", json={"email": "admin@test.com", "password": "AdminPass1!"})
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(autouse=True)
def reset_users_store():
    original = {k: v.copy() for k, v in users_store.items()}
    yield
    users_store.clear()
    users_store.update(original)


# ---------------------------------------------------------------------------
# POST /auth/login — contract
# ---------------------------------------------------------------------------

class TestLoginContract:
    def test_200_response_matches_schema(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        assert r.status_code == 200
        body = r.json()
        live_schema = infer_schema(body)
        drift = find_schema_drift(LOGIN_200_SCHEMA, live_schema)
        assert not drift, f"Contract drift on POST /auth/login: {drift}"

    def test_401_response_is_json(self, client):
        r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
        assert r.status_code == 401
        assert "application/json" in r.headers.get("content-type", "")

    def test_401_has_standard_error_shape(self, client):
        r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
        body = r.json()
        assert "detail" in body or "message" in body or "error" in body, \
            f"Non-standard error shape: {list(body.keys())}"

    def test_no_sensitive_fields_in_200(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        body = r.json()
        for field in ["password", "hashed_password", "salt", "secret"]:
            assert field not in body, f"Sensitive field '{field}' in login response"

    def test_token_is_string(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        assert isinstance(r.json()["token"], str)
        assert len(r.json()["token"]) > 10

    def test_content_type_is_json(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /auth/me — contract
# ---------------------------------------------------------------------------

class TestMeContract:
    def test_200_matches_schema(self, client, user_headers):
        r = client.get("/auth/me", headers=user_headers)
        assert r.status_code == 200
        live_schema = infer_schema(r.json())
        drift = find_schema_drift(ME_200_SCHEMA, live_schema)
        assert not drift, f"Contract drift on GET /auth/me: {drift}"

    def test_content_type_is_json(self, client, user_headers):
        r = client.get("/auth/me", headers=user_headers)
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /users/ — contract
# ---------------------------------------------------------------------------

class TestUsersListContract:
    def test_200_matches_schema(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        assert r.status_code == 200
        live_schema = infer_schema(r.json())
        drift = find_schema_drift(USERS_LIST_200_SCHEMA, live_schema)
        assert not drift, f"Contract drift on GET /users/: {drift}"

    def test_items_not_null(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        for item in r.json()["items"]:
            assert item is not None

    def test_items_match_user_schema(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        for item in r.json()["items"]:
            item_schema = infer_schema(item)
            drift = find_schema_drift(USER_OBJECT_SCHEMA, item_schema)
            assert not drift, f"User object schema drift: {drift}"

    def test_content_type_is_json(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /users/{user_id} — contract
# ---------------------------------------------------------------------------

class TestGetUserContract:
    def test_200_matches_user_schema(self, client, user_headers):
        r = client.get("/users/1", headers=user_headers)
        assert r.status_code == 200
        live_schema = infer_schema(r.json())
        drift = find_schema_drift(USER_OBJECT_SCHEMA, live_schema)
        assert not drift, f"Contract drift on GET /users/1: {drift}"

    def test_404_is_json(self, client, user_headers):
        r = client.get("/users/9999", headers=user_headers)
        assert r.status_code == 404
        assert "application/json" in r.headers.get("content-type", "")

    def test_404_has_standard_error_shape(self, client, user_headers):
        r = client.get("/users/9999", headers=user_headers)
        body = r.json()
        assert "detail" in body or "message" in body or "error" in body


# ---------------------------------------------------------------------------
# PUT /users/{user_id} — contract
# ---------------------------------------------------------------------------

class TestUpdateUserContract:
    def test_200_matches_user_schema(self, client, user_headers):
        r = client.put("/users/1", json={"name": "Updated"}, headers=user_headers)
        assert r.status_code == 200
        live_schema = infer_schema(r.json())
        drift = find_schema_drift(USER_OBJECT_SCHEMA, live_schema)
        assert not drift, f"Contract drift on PUT /users/1: {drift}"

    def test_403_is_json(self, client, user_headers):
        r = client.put("/users/2", json={"name": "Hacked"}, headers=user_headers)
        assert r.status_code == 403
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# DELETE /users/{user_id} — contract
# ---------------------------------------------------------------------------

class TestDeleteUserContract:
    def test_200_has_deleted_field(self, client, admin_headers):
        r = client.delete("/users/1", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "deleted" in body
        assert isinstance(body["deleted"], int)

    def test_403_is_json(self, client, user_headers):
        r = client.delete("/users/1", headers=user_headers)
        assert r.status_code == 403
        assert "application/json" in r.headers.get("content-type", "")
