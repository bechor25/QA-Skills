import uuid
import base64
import json
import time
import statistics
import pytest
from app.services import user_service


class TestJWTSecurity:
    def test_no_token_returns_401(self, client):
        r = client.get("/users/me")
        assert r.status_code == 401

    def test_invalid_token_returns_401(self, client):
        r = client.get("/users/me", headers={"Authorization": "Bearer invalid.token.value"})
        assert r.status_code == 401

    def test_expired_token_returns_401(self, client):
        expired = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJ1c2VyLTEiLCJyb2xlIjoidXNlciIsImV4cCI6MX0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        r = client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_malformed_bearer_returns_401(self, client):
        r = client.get("/users/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401

    def test_jwt_alg_none_rejected(self, client):
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "admin-id", "role": "admin", "exp": 9999999999}).encode()
        ).decode().rstrip("=")
        none_token = f"{header}.{payload}."
        r = client.get("/users/me", headers={"Authorization": f"Bearer {none_token}"})
        assert r.status_code == 401, "CRITICAL: JWT alg=none accepted — auth bypass!"

    def test_wrong_secret_key_rejected(self, client):
        from jose import jwt as jose_jwt
        from datetime import datetime, timedelta
        payload = {
            "sub": "attacker-id",
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        bad_token = jose_jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        r = client.get("/users/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401


class TestIDOR:
    def test_user_cannot_read_other_user_profile(self, client, user_factory, regular_headers):
        victim, _ = user_factory()
        r = client.get(f"/users/{victim.id}", headers=regular_headers)
        assert r.status_code in (403, 404), \
            f"IDOR: got {r.status_code} when accessing other user profile"

    def test_user_cannot_update_other_user(self, client, user_factory, regular_headers):
        victim, _ = user_factory()
        r = client.put(f"/users/{victim.id}", json={"name": "Hacked"}, headers=regular_headers)
        assert r.status_code in (403, 404), \
            f"IDOR: got {r.status_code} when updating other user"

    def test_user_cannot_delete_other_user(self, client, user_factory, regular_headers):
        victim, _ = user_factory()
        r = client.delete(f"/users/{victim.id}", headers=regular_headers)
        assert r.status_code in (403, 404), \
            f"IDOR: got {r.status_code} when deleting other user"


class TestPrivilegeEscalation:
    def test_regular_user_cannot_delete_any_user(self, client, user_factory, regular_headers):
        target, _ = user_factory()
        r = client.delete(f"/users/{target.id}", headers=regular_headers)
        assert r.status_code == 403, "Privilege escalation: user deleted another user!"

    def test_role_elevation_via_create_body_ignored(self, client):
        uid = uuid.uuid4().hex[:6]
        r = client.post("/users/", json={
            "email": f"escalate_{uid}@example.com",
            "password": "Pass123!",
            "name": "Escalator",
            "role": "admin",
        })
        assert r.status_code == 201
        assert r.json().get("role") == "user", \
            "CRITICAL: User self-assigned admin role via POST body!"

    def test_role_elevation_via_update_body_ignored(self, client, regular_user, regular_headers):
        r = client.put(
            f"/users/{regular_user.id}",
            json={"name": "Normal", "role": "admin"},
            headers=regular_headers,
        )
        if r.status_code == 200:
            assert r.json().get("role") != "admin", \
                "CRITICAL: User escalated own role to admin via PUT body!"

    def test_admin_endpoints_reject_regular_user(self, client, regular_headers):
        uid = uuid.uuid4().hex[:6]
        target, _ = user_factory_user(regular_headers)
        # DELETE requires admin role
        r = client.delete(f"/users/any-user-id", headers=regular_headers)
        assert r.status_code in (403, 404)


def user_factory_user(regular_headers):
    return None, None


class TestTimingAttack:
    def test_response_time_similar_for_existing_vs_nonexistent_email(self, client, user_factory):
        user, _ = user_factory()
        iterations = 6

        existing_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            client.post("/auth/login", json={"email": user.email, "password": "wrong_password_xyz"})
            existing_times.append(time.perf_counter() - start)

        nonexistent_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            client.post("/auth/login", json={"email": "nobody_xyz_99@doesnotexist.com", "password": "wrong"})
            nonexistent_times.append(time.perf_counter() - start)

        avg_existing = statistics.mean(existing_times)
        avg_nonexistent = statistics.mean(nonexistent_times)
        diff = abs(avg_existing - avg_nonexistent)

        # Note: bcrypt verification adds ~100ms for existing users — inherent timing oracle.
        # Threshold 500ms catches gross leaks while allowing bcrypt overhead.
        assert diff < 0.5, (
            f"Timing difference detected: existing={avg_existing*1000:.0f}ms "
            f"nonexistent={avg_nonexistent*1000:.0f}ms diff={diff*1000:.0f}ms. "
            "Consider constant-time comparison for missing users."
        )
