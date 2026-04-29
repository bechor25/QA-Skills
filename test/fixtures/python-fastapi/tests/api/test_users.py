import uuid
import pytest
from app.services import user_service


class TestGetUsersMe:
    def test_authenticated_returns_current_user(self, client, regular_user, regular_headers):
        r = client.get("/users/me", headers=regular_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == regular_user.id
        assert body["email"] == regular_user.email
        assert body["name"] == regular_user.name

    def test_no_auth_returns_401(self, client):
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

    def test_password_hash_not_in_response(self, client, regular_headers):
        r = client.get("/users/me", headers=regular_headers)
        body = r.json()
        assert "password_hash" not in body
        assert "password" not in body

    def test_response_contains_expected_fields(self, client, regular_headers):
        r = client.get("/users/me", headers=regular_headers)
        body = r.json()
        assert "id" in body
        assert "email" in body
        assert "name" in body
        assert "role" in body


class TestGetUsersList:
    def test_authenticated_returns_list(self, client, regular_headers):
        r = client.get("/users/", headers=regular_headers)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)

    def test_no_auth_returns_401(self, client):
        r = client.get("/users/")
        assert r.status_code == 401

    def test_pagination_limit_respected(self, client, regular_headers):
        r = client.get("/users/?page=1&limit=2", headers=regular_headers)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 2

    def test_large_page_returns_empty_items(self, client, regular_headers):
        r = client.get("/users/?page=9999&limit=10", headers=regular_headers)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_items_have_no_sensitive_fields(self, client, regular_headers):
        r = client.get("/users/", headers=regular_headers)
        for user in r.json()["items"]:
            assert "password" not in user
            assert "password_hash" not in user

    def test_get_is_readonly(self, client, regular_headers):
        before = client.get("/users/", headers=regular_headers).json()["total"]
        client.get("/users/", headers=regular_headers)
        after = client.get("/users/", headers=regular_headers).json()["total"]
        assert before == after


class TestPostUsers:
    def test_creates_user_successfully(self, client):
        uid = uuid.uuid4().hex[:8]
        r = client.post("/users/", json={
            "email": f"create_{uid}@example.com",
            "password": "NewPass1!",
            "name": "New User",
        })
        assert r.status_code == 201
        body = r.json()
        assert "id" in body
        assert body["email"] == f"create_{uid}@example.com"
        assert body["role"] == "user"

    def test_duplicate_email_returns_400(self, client, regular_user):
        r = client.post("/users/", json={
            "email": regular_user.email,
            "password": "Pass123!",
            "name": "Duplicate",
        })
        assert r.status_code == 400

    def test_missing_email_returns_422(self, client):
        r = client.post("/users/", json={"password": "Pass123!", "name": "No Email"})
        assert r.status_code == 422

    def test_missing_password_returns_422(self, client):
        r = client.post("/users/", json={"email": "x@x.com", "name": "No Pass"})
        assert r.status_code == 422

    def test_missing_name_returns_422(self, client):
        r = client.post("/users/", json={"email": "x@x.com", "password": "Pass123!"})
        assert r.status_code == 422

    def test_invalid_email_format_returns_422(self, client):
        r = client.post("/users/", json={"email": "not-email", "password": "Pass1!", "name": "Bad"})
        assert r.status_code == 422

    def test_empty_body_returns_422(self, client):
        r = client.post("/users/", json={})
        assert r.status_code == 422

    def test_mass_assignment_role_ignored(self, client):
        uid = uuid.uuid4().hex[:8]
        r = client.post("/users/", json={
            "email": f"masstest_{uid}@example.com",
            "password": "Pass123!",
            "name": "Mass Test",
            "role": "admin",
        })
        assert r.status_code == 201
        assert r.json().get("role") != "admin"

    def test_password_not_in_response(self, client):
        uid = uuid.uuid4().hex[:8]
        r = client.post("/users/", json={
            "email": f"passcheck_{uid}@example.com",
            "password": "MySecret123!",
            "name": "Pass Check",
        })
        assert r.status_code == 201
        body = r.json()
        assert "password" not in body
        assert "password_hash" not in body

    def test_oversized_name_does_not_crash(self, client):
        uid = uuid.uuid4().hex[:8]
        r = client.post("/users/", json={
            "email": f"bigname_{uid}@example.com",
            "password": "Pass123!",
            "name": "x" * 10001,
        })
        assert r.status_code in (201, 400, 422)
        assert r.status_code != 500


class TestGetUserById:
    def test_user_can_get_own_profile(self, client, regular_user, regular_headers):
        r = client.get(f"/users/{regular_user.id}", headers=regular_headers)
        assert r.status_code == 200
        assert r.json()["id"] == regular_user.id

    def test_admin_can_get_any_user(self, client, regular_user, admin_headers):
        r = client.get(f"/users/{regular_user.id}", headers=admin_headers)
        assert r.status_code == 200

    def test_user_cannot_get_other_user_returns_403(self, client, user_factory, regular_headers):
        other, _ = user_factory()
        r = client.get(f"/users/{other.id}", headers=regular_headers)
        assert r.status_code == 403

    def test_nonexistent_id_returns_404(self, client, admin_headers):
        r = client.get("/users/nonexistent-uuid-99999", headers=admin_headers)
        assert r.status_code == 404

    def test_no_auth_returns_401(self, client, regular_user):
        r = client.get(f"/users/{regular_user.id}")
        assert r.status_code == 401

    def test_response_omits_password_hash(self, client, regular_user, regular_headers):
        r = client.get(f"/users/{regular_user.id}", headers=regular_headers)
        assert "password_hash" not in r.json()


class TestPutUserById:
    def test_user_can_update_own_name(self, client, regular_user, regular_headers):
        r = client.put(
            f"/users/{regular_user.id}",
            json={"name": "Updated Name"},
            headers=regular_headers,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_user_cannot_update_other_user(self, client, user_factory, regular_headers):
        other, _ = user_factory()
        r = client.put(f"/users/{other.id}", json={"name": "Hacked"}, headers=regular_headers)
        assert r.status_code == 403

    def test_admin_can_update_any_user(self, client, regular_user, admin_headers):
        r = client.put(
            f"/users/{regular_user.id}",
            json={"name": "Admin Updated"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Admin Updated"

    def test_idempotent_update(self, client, regular_user, regular_headers):
        r1 = client.put(f"/users/{regular_user.id}", json={"name": "Stable"}, headers=regular_headers)
        r2 = client.put(f"/users/{regular_user.id}", json={"name": "Stable"}, headers=regular_headers)
        assert r1.json()["name"] == r2.json()["name"]

    def test_nonexistent_user_returns_404(self, client, admin_headers):
        r = client.put("/users/nonexistent-99999", json={"name": "Ghost"}, headers=admin_headers)
        assert r.status_code == 404

    def test_no_auth_returns_401(self, client, regular_user):
        r = client.put(f"/users/{regular_user.id}", json={"name": "NoAuth"})
        assert r.status_code == 401


class TestDeleteUserById:
    def test_admin_can_delete_user(self, client, user_factory, admin_headers):
        user, _ = user_factory()
        r = client.delete(f"/users/{user.id}", headers=admin_headers)
        assert r.status_code == 204

    def test_regular_user_cannot_delete_returns_403(self, client, user_factory, regular_headers):
        other, _ = user_factory()
        r = client.delete(f"/users/{other.id}", headers=regular_headers)
        assert r.status_code == 403

    def test_nonexistent_user_returns_404(self, client, admin_headers):
        r = client.delete("/users/nonexistent-99999", headers=admin_headers)
        assert r.status_code == 404

    def test_no_auth_returns_401(self, client, regular_user):
        r = client.delete(f"/users/{regular_user.id}")
        assert r.status_code == 401

    def test_deleted_user_no_longer_accessible(self, client, user_factory, admin_headers):
        user, _ = user_factory()
        client.delete(f"/users/{user.id}", headers=admin_headers)
        r = client.get(f"/users/{user.id}", headers=admin_headers)
        assert r.status_code == 404
