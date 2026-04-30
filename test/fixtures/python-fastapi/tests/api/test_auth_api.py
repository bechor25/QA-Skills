import pytest
from fastapi.testclient import TestClient

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from main import app

EXPIRED_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxIiwicm9sZSI6InVzZXIiLCJleHAiOjF9"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


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


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

class TestLoginEndpoint:
    def test_valid_user_returns_200_with_token(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert isinstance(body["token"], str)
        assert "user_id" in body

    def test_valid_admin_returns_200(self, client):
        r = client.post("/auth/login", json={"email": "admin@test.com", "password": "AdminPass1!"})
        assert r.status_code == 200

    def test_wrong_password_returns_401(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "WrongPass!"})
        assert r.status_code == 401

    def test_unknown_email_returns_401(self, client):
        r = client.post("/auth/login", json={"email": "nobody@test.com", "password": "TestPass1!"})
        assert r.status_code == 401

    def test_missing_password_returns_422(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com"})
        assert r.status_code == 422

    def test_missing_email_returns_422(self, client):
        r = client.post("/auth/login", json={"password": "TestPass1!"})
        assert r.status_code == 422

    def test_empty_body_returns_422(self, client):
        r = client.post("/auth/login", content=b"", headers={"Content-Type": "application/json"})
        assert r.status_code == 422

    def test_invalid_json_returns_422(self, client):
        r = client.post("/auth/login", content=b"}{invalid", headers={"Content-Type": "application/json"})
        assert r.status_code == 422

    def test_response_does_not_contain_stack_trace(self, client):
        r = client.post("/auth/login", json={"email": "bad@test.com", "password": "wrong"})
        assert "Traceback" not in r.text
        assert "traceback" not in r.text

    def test_error_response_does_not_expose_password(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "MySecret123!"})
        assert "MySecret123!" not in r.text

    def test_response_content_type_is_json(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        assert "application/json" in r.headers.get("content-type", "")

    @pytest.mark.parametrize("payload", [
        "' OR '1'='1",
        "admin'--",
        "'; DROP TABLE users; --",
    ])
    def test_sql_injection_in_email_returns_401(self, client, payload):
        r = client.post("/auth/login", json={"email": payload, "password": payload})
        assert r.status_code in (400, 401, 422)
        if r.status_code == 200:
            assert "token" not in r.json()


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

class TestMeEndpoint:
    def test_valid_token_returns_user_info(self, client, user_headers):
        r = client.get("/auth/me", headers=user_headers)
        assert r.status_code == 200
        body = r.json()
        assert "user_id" in body
        assert "role" in body

    def test_no_token_returns_403_or_401(self, client):
        r = client.get("/auth/me")
        assert r.status_code in (401, 403)

    def test_invalid_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401

    def test_expired_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {EXPIRED_JWT}"})
        assert r.status_code == 401

    def test_admin_token_returns_admin_role(self, client, admin_headers):
        r = client.get("/auth/me", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_get_me_is_readonly(self, client, user_headers):
        r1 = client.get("/auth/me", headers=user_headers)
        r2 = client.get("/auth/me", headers=user_headers)
        assert r1.json() == r2.json()
