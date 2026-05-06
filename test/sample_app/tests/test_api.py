"""API integration tests — uses FastAPI TestClient (no live server needed)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.users import store


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the user store before each test for isolation."""
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
def admin_token(client):
    store.create("admin@test.com", "Admin", "adminpass1", role="admin")
    resp = client.post("/api/login", json={"email": "admin@test.com", "password": "adminpass1"})
    return resp.json()["access_token"]


@pytest.fixture()
def user_token(client):
    store.create("user@test.com", "User", "userpass1")
    resp = client.post("/api/login", json={"email": "user@test.com", "password": "userpass1"})
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/api/register", json={
            "email": "new@test.com",
            "name": "New User",
            "password": "securepassword"
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@test.com"
        assert body["name"] == "New User"
        assert body["role"] == "user"
        assert "id" in body
        assert "password" not in body
        assert "password_hash" not in body

    def test_register_duplicate_email(self, client):
        payload = {"email": "dup@test.com", "name": "Dup", "password": "securepass"}
        client.post("/api/register", json=payload)
        resp = client.post("/api/register", json=payload)
        assert resp.status_code == 409

    def test_register_invalid_email(self, client):
        resp = client.post("/api/register", json={
            "email": "not-an-email",
            "name": "User",
            "password": "securepassword"
        })
        assert resp.status_code == 422

    def test_register_short_password(self, client):
        resp = client.post("/api/register", json={
            "email": "x@test.com",
            "name": "X",
            "password": "short"  # < 8 chars
        })
        assert resp.status_code == 422

    def test_register_empty_name(self, client):
        resp = client.post("/api/register", json={
            "email": "x@test.com",
            "name": "",
            "password": "securepassword"
        })
        assert resp.status_code == 422

    def test_register_missing_fields(self, client):
        resp = client.post("/api/register", json={"email": "x@test.com"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        store.create("login@test.com", "Login", "loginpass1")
        resp = client.post("/api/login", json={"email": "login@test.com", "password": "loginpass1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        store.create("x@test.com", "X", "correct_pass")
        resp = client.post("/api/login", json={"email": "x@test.com", "password": "wrong_pass"})
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = client.post("/api/login", json={"email": "ghost@test.com", "password": "anything"})
        assert resp.status_code == 401

    def test_login_missing_body(self, client):
        resp = client.post("/api/login", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/me
# ---------------------------------------------------------------------------

class TestMe:
    def test_me_authenticated(self, client, user_token):
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "user@test.com"

    def test_me_no_token(self, client):
        resp = client.get("/api/me")
        assert resp.status_code == 401

    def test_me_bad_token(self, client):
        resp = client.get("/api/me", headers={"Authorization": "Bearer invalid.token.value"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/users (admin only)
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_admin_can_list(self, client, admin_token):
        resp = client.get("/api/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_regular_user_forbidden(self, client, user_token):
        resp = client.get("/api/users", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403

    def test_unauthenticated_forbidden(self, client):
        resp = client.get("/api/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/users/{user_id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_user_can_get_self(self, client, user_token):
        user_id = store.get_by_email("user@test.com").id
        resp = client.get(f"/api/users/{user_id}", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert resp.json()["id"] == user_id

    def test_user_cannot_get_other(self, client, user_token, admin_token):
        admin_id = store.get_by_email("admin@test.com").id
        resp = client.get(f"/api/users/{admin_id}", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403

    def test_admin_can_get_any(self, client, admin_token):
        other = store.create("other@test.com", "Other", "otherpass1")
        resp = client.get(f"/api/users/{other.id}", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_nonexistent_user(self, client, admin_token):
        resp = client.get("/api/users/99999", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/calc/quote
# ---------------------------------------------------------------------------

class TestCalcQuote:
    def test_basic_quote(self, client):
        resp = client.post("/api/calc/quote", json={
            "price": 100.0,
            "discount_pct": 10.0,
            "tax_rate": 0.17
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["discounted"] == 90.0
        assert body["tax"] == pytest.approx(15.3, abs=0.01)
        assert body["total"] == pytest.approx(105.3, abs=0.01)

    def test_zero_discount_default_tax(self, client):
        resp = client.post("/api/calc/quote", json={"price": 100.0})
        assert resp.status_code == 200
        body = resp.json()
        assert body["discounted"] == 100.0
        assert body["total"] == pytest.approx(117.0, abs=0.01)

    def test_negative_price_rejected(self, client):
        resp = client.post("/api/calc/quote", json={"price": -1.0})
        assert resp.status_code == 422

    def test_discount_above_100_rejected(self, client):
        resp = client.post("/api/calc/quote", json={"price": 100.0, "discount_pct": 101.0})
        assert resp.status_code == 422

    def test_tax_rate_above_1_rejected(self, client):
        resp = client.post("/api/calc/quote", json={"price": 100.0, "tax_rate": 1.5})
        assert resp.status_code == 422

    def test_zero_price(self, client):
        resp = client.post("/api/calc/quote", json={"price": 0.0})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0.0

    def test_full_discount(self, client):
        resp = client.post("/api/calc/quote", json={"price": 100.0, "discount_pct": 100.0})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0.0


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

class TestHTMLPages:
    def test_index_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_quote_page(self, client):
        resp = client.get("/quote")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_openapi_json(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert "paths" in schema
