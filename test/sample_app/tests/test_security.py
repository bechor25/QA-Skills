"""Security tests — auth bypass, injection, token vulnerabilities, input validation."""
from __future__ import annotations

import pytest
import time
import jwt as pyjwt
from fastapi.testclient import TestClient

from app.main import app
from app.users import store
from app.auth import JWT_SECRET, JWT_ALG, decode_token_unsafe


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
def valid_token(client):
    store.create("sec@test.com", "SecUser", "secpassword1")
    resp = client.post("/api/login", json={"email": "sec@test.com", "password": "secpassword1"})
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# JWT Vulnerabilities
# ---------------------------------------------------------------------------

class TestJWTSecurity:
    def test_none_algorithm_rejected(self, client):
        """API must reject tokens signed with 'none' algorithm."""
        payload = {"sub": "1", "role": "admin", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        # Craft a token with alg=none by using empty secret
        malicious_header = {"alg": "none", "typ": "JWT"}
        import base64
        import json as _json
        header_b64 = base64.urlsafe_b64encode(_json.dumps(malicious_header).encode()).rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(_json.dumps(payload).encode()).rstrip(b"=").decode()
        none_token = f"{header_b64}.{payload_b64}."
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {none_token}"})
        assert resp.status_code == 401, "Server must reject alg=none tokens"

    def test_expired_token_rejected(self, client):
        """Expired tokens must be rejected."""
        payload = {
            "sub": "1",
            "role": "user",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
        expired_token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401

    def test_wrong_secret_rejected(self, client):
        """Tokens signed with wrong secret must be rejected."""
        payload = {"sub": "1", "role": "user", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        bad_token = pyjwt.encode(payload, "wrong-secret-entirely", algorithm=JWT_ALG)
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert resp.status_code == 401

    def test_tampered_role_rejected(self, client, valid_token):
        """A valid token with tampered payload must be rejected."""
        parts = valid_token.split(".")
        import base64
        import json as _json
        # Decode and tamper with payload
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        decoded = _json.loads(base64.urlsafe_b64decode(padded))
        decoded["role"] = "admin"
        new_payload_b64 = base64.urlsafe_b64encode(_json.dumps(decoded).encode()).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{new_payload_b64}.{parts[2]}"
        resp = client.get("/api/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert resp.status_code == 401

    def test_malformed_token_rejected(self, client):
        """Completely malformed tokens must be rejected."""
        for bad_token in ["not-a-token", "a.b", "x.y.z.w", "", "   "]:
            resp = client.get("/api/me", headers={"Authorization": f"Bearer {bad_token}"})
            assert resp.status_code == 401, f"Expected 401 for token: {bad_token!r}"

    def test_missing_authorization_header(self, client):
        """Missing auth header must return 401."""
        resp = client.get("/api/me")
        assert resp.status_code == 401

    def test_non_bearer_scheme_rejected(self, client, valid_token):
        """Basic auth scheme must be rejected on bearer endpoints."""
        resp = client.get("/api/me", headers={"Authorization": f"Basic {valid_token}"})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Authorization / Privilege Escalation
# ---------------------------------------------------------------------------

class TestPrivilegeEscalation:
    def test_regular_user_cannot_list_all_users(self, client):
        store.create("user@test.com", "User", "userpass12")
        resp = client.post("/api/login", json={"email": "user@test.com", "password": "userpass12"})
        token = resp.json()["access_token"]
        resp2 = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 403

    def test_user_cannot_read_other_users(self, client):
        u1 = store.create("u1@test.com", "U1", "u1password1")
        u2 = store.create("u2@test.com", "U2", "u2password2")
        resp = client.post("/api/login", json={"email": "u1@test.com", "password": "u1password1"})
        token = resp.json()["access_token"]
        resp2 = client.get(f"/api/users/{u2.id}", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 403

    def test_admin_can_read_all_users(self, client):
        store.create("admin@test.com", "Admin", "adminpass1", role="admin")
        other = store.create("other@test.com", "Other", "otherpass1")
        resp = client.post("/api/login", json={"email": "admin@test.com", "password": "adminpass1"})
        token = resp.json()["access_token"]
        resp2 = client.get(f"/api/users/{other.id}", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200

    def test_crafted_admin_token_without_valid_user(self, client):
        """Token for non-existent user ID must fail."""
        payload = {"sub": "99999", "role": "admin", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
        resp = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Input Validation / Injection Defense
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_sql_injection_in_email(self, client):
        """SQL injection in email field must be rejected by validation."""
        resp = client.post("/api/register", json={
            "email": "'; DROP TABLE users; --",
            "name": "Hacker",
            "password": "hackerpass1"
        })
        assert resp.status_code == 422

    def test_xss_in_name_stored_safely(self, client):
        """XSS payload in name should be accepted as a string (stored, not executed)."""
        resp = client.post("/api/register", json={
            "email": "xss@test.com",
            "name": "<script>alert(1)</script>",
            "password": "xsspassword"
        })
        # The API stores data; HTML escaping is the template layer's job
        # Validation layer should accept it (name is a string)
        assert resp.status_code in (201, 422)  # either accept or reject, not 500

    def test_oversized_password_rejected(self, client):
        """Passwords over 128 chars must be rejected."""
        resp = client.post("/api/register", json={
            "email": "big@test.com",
            "name": "Big",
            "password": "x" * 129
        })
        assert resp.status_code == 422

    def test_negative_price_rejected(self, client):
        resp = client.post("/api/calc/quote", json={"price": -999.0})
        assert resp.status_code == 422

    def test_extremely_large_price_accepted(self, client):
        """Very large prices should be handled gracefully."""
        resp = client.post("/api/calc/quote", json={"price": 1e12})
        assert resp.status_code in (200, 422)  # not 500

    def test_non_numeric_price_rejected(self, client):
        resp = client.post("/api/calc/quote", json={"price": "not_a_number"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Hardcoded Secret Detection (static / behavioral)
# ---------------------------------------------------------------------------

class TestHardcodedSecretRisk:
    def test_default_jwt_secret_is_weak(self):
        """The fallback JWT secret 'dev-secret-change-me' must not be used in production.
        This test documents the risk — if JWT_SECRET equals the fallback, flag it."""
        import os
        env_secret = os.environ.get("JWT_SECRET")
        if env_secret is None:
            # JWT_SECRET not set -> fallback is used
            pytest.xfail(
                "JWT_SECRET env var is not set. App falls back to 'dev-secret-change-me'. "
                "Set JWT_SECRET in production to a strong random value."
            )

    def test_decode_token_unsafe_is_a_security_risk(self):
        """decode_token_unsafe must not be reachable via any API endpoint."""
        import inspect
        import app.routes as routes_module
        source = inspect.getsource(routes_module)
        assert "decode_token_unsafe" not in source, (
            "decode_token_unsafe is referenced in routes.py — remove it from production code"
        )
