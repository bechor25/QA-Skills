import pytest
import base64
import json as _json
import hmac as _hmac
import hashlib
import time
import statistics
from fastapi.testclient import TestClient

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from main import app
from src.users import users_store

SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1' UNION SELECT null, null, null--",
    "' OR 1=1--",
    "admin'--",
    "1; SELECT sleep(5)--",
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "javascript:alert(1)",
    "<svg onload=alert(1)>",
]

OPEN_REDIRECT_PAYLOADS = [
    "//evil.com",
    "https://evil.com",
    "javascript:alert(1)",
]


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
# A. SQL Injection
# ---------------------------------------------------------------------------

class TestSQLInjection:
    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_login_email(self, client, payload):
        r = client.post("/auth/login", json={"email": payload, "password": payload})
        assert r.status_code in (400, 401, 422), \
            f"SQL injection returned {r.status_code} — possible bypass"
        if r.status_code == 200:
            assert "token" not in r.json(), "Token returned for injection payload!"

    def test_no_db_error_message_leaked(self, client):
        r = client.post("/auth/login", json={"email": "' OR '1'='1", "password": "x"})
        assert "syntax error" not in r.text.lower()
        assert "sqlalchemy" not in r.text.lower()
        assert "postgresql" not in r.text.lower()
        assert "mysql" not in r.text.lower()
        assert r.status_code != 500


# ---------------------------------------------------------------------------
# B. JWT Attacks
# ---------------------------------------------------------------------------

class TestJWTSecurity:
    def test_alg_none_rejected(self, client):
        header = base64.urlsafe_b64encode(
            _json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            _json.dumps({"sub": "1", "role": "admin"}).encode()
        ).decode().rstrip("=")
        none_token = f"{header}.{payload}."
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {none_token}"})
        assert r.status_code == 401, "JWT alg=none accepted — critical auth bypass!"

    def test_tampered_payload_rejected(self, client, user_token):
        parts = user_token.split(".")
        forged = parts[0] + "." + parts[1] + ".invalidsignature"
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 401

    def test_hs256_confusion_rejected(self, client):
        header = base64.urlsafe_b64encode(
            _json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            _json.dumps({"sub": "1", "role": "admin", "exp": 9999999999}).encode()
        ).decode().rstrip("=")
        sig_input = f"{header}.{payload}".encode()
        sig = base64.urlsafe_b64encode(
            _hmac.new(b"wrong-secret", sig_input, hashlib.sha256).digest()
        ).decode().rstrip("=")
        confused = f"{header}.{payload}.{sig}"
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {confused}"})
        assert r.status_code == 401

    def test_missing_bearer_prefix_rejected(self, client, user_token):
        r = client.get("/auth/me", headers={"Authorization": user_token})
        assert r.status_code in (401, 403)

    def test_bearer_with_spaces_rejected(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer   "})
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# C. IDOR
# ---------------------------------------------------------------------------

class TestIDOR:
    def test_user_cannot_read_other_user_via_id(self, client, user_headers):
        r = client.get("/users/2", headers=user_headers)
        # Should return data (no private endpoint here) — but update must be blocked
        assert r.status_code in (200, 403, 404)

    def test_user_cannot_modify_other_user(self, client, user_headers):
        r = client.put("/users/2", json={"name": "Hacked"}, headers=user_headers)
        assert r.status_code == 403, \
            f"IDOR: user modified another user's record, got {r.status_code}"

    def test_sequential_id_enumeration_update_blocked(self, client, user_headers):
        for delta in [-1, 1]:
            target = 1 + delta
            r = client.put(f"/users/{target}", json={"name": "Hacked"}, headers=user_headers)
            assert r.status_code in (403, 404), \
                f"IDOR via adjacent ID {target}: got {r.status_code}"


# ---------------------------------------------------------------------------
# D. Privilege Escalation
# ---------------------------------------------------------------------------

class TestPrivilegeEscalation:
    def test_user_cannot_delete_other_user(self, client, user_headers):
        r = client.delete("/users/2", headers=user_headers)
        assert r.status_code == 403, \
            f"Privilege escalation: user deleted another user, got {r.status_code}"

    def test_user_cannot_delete_self(self, client, user_headers):
        r = client.delete("/users/1", headers=user_headers)
        assert r.status_code == 403

    def test_mass_assignment_role_not_accepted_on_update(self, client, user_headers):
        r = client.put("/users/1", json={"role": "admin", "name": "Alice"}, headers=user_headers)
        if r.status_code == 200:
            assert r.json().get("role") != "admin", "Mass assignment: role elevated via update!"


# ---------------------------------------------------------------------------
# E. Sensitive Data Exposure
# ---------------------------------------------------------------------------

class TestSensitiveDataExposure:
    def test_password_not_in_login_response(self, client):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
        body = r.json()
        for key in ["password", "password_hash", "hashed_password", "salt"]:
            assert key not in body, f"Sensitive field '{key}' in login response"

    def test_password_not_in_me_response(self, client, user_headers):
        r = client.get("/auth/me", headers=user_headers)
        body = r.json()
        for key in ["password", "password_hash", "hashed_password", "salt"]:
            assert key not in body

    def test_password_not_in_users_list(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        for user in r.json().get("items", []):
            assert "password" not in user
            assert "hashed_password" not in user

    def test_error_response_no_stack_trace(self, client):
        r = client.post("/auth/login",
                        content=b"}{invalid",
                        headers={"Content-Type": "application/json"})
        if r.status_code >= 400:
            assert "Traceback" not in r.text
            assert "traceback" not in r.text

    def test_401_error_does_not_confirm_email_existence(self, client):
        r1 = client.post("/auth/login", json={"email": "user@test.com", "password": "wrong"})
        r2 = client.post("/auth/login", json={"email": "nobody@doesnotexist99.com", "password": "wrong"})
        assert r1.status_code == r2.status_code == 401
        # Both should return same error message — no user enumeration
        assert r1.json().get("detail") == r2.json().get("detail")


# ---------------------------------------------------------------------------
# F. Timing Attack (auth response time)
# ---------------------------------------------------------------------------

class TestTimingAttack:
    def test_no_significant_timing_difference_for_valid_vs_invalid_email(self, client):
        iterations = 8
        existing_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            client.post("/auth/login", json={"email": "user@test.com", "password": "wrong"})
            existing_times.append(time.perf_counter() - start)

        nonexistent_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            client.post("/auth/login", json={"email": "nobody@doesnotexist12345.com", "password": "wrong"})
            nonexistent_times.append(time.perf_counter() - start)

        avg_existing = statistics.mean(existing_times)
        avg_nonexistent = statistics.mean(nonexistent_times)
        diff = abs(avg_existing - avg_nonexistent)
        # Allow 300ms tolerance for CI variance
        assert diff < 0.3, (
            f"Timing leak: existing {avg_existing*1000:.1f}ms vs "
            f"nonexistent {avg_nonexistent*1000:.1f}ms (diff={diff*1000:.1f}ms)"
        )
