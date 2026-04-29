import uuid
import pytest


class TestPasswordNotExposed:
    def test_password_hash_not_in_me_response(self, client, regular_headers):
        r = client.get("/users/me", headers=regular_headers)
        assert r.status_code == 200
        body = r.json()
        for key in ("password", "password_hash", "passwordHash", "salt", "secret"):
            assert key not in body, f"Sensitive field '{key}' exposed in /users/me"

    def test_password_hash_not_in_list_response(self, client, regular_headers):
        r = client.get("/users/", headers=regular_headers)
        assert r.status_code == 200
        for user in r.json().get("items", []):
            assert "password" not in user
            assert "password_hash" not in user

    def test_password_hash_not_in_user_detail_response(self, client, regular_user, admin_headers):
        r = client.get(f"/users/{regular_user.id}", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert "password_hash" not in body
        assert "password" not in body

    def test_password_hash_not_in_create_response(self, client):
        uid = uuid.uuid4().hex[:6]
        r = client.post("/users/", json={
            "email": f"expose_{uid}@example.com",
            "password": "SuperSecret1!",
            "name": "Expose Test",
        })
        assert r.status_code == 201
        body = r.json()
        assert "password" not in body
        assert "password_hash" not in body

    def test_login_error_does_not_echo_password(self, client):
        r = client.post("/auth/login", json={"email": "x@x.com", "password": "TryToLeakMe"})
        assert r.status_code in (400, 401, 422)
        assert "TryToLeakMe" not in r.text
        assert "hash" not in r.text.lower()


class TestStackTraceNotExposed:
    def test_invalid_json_no_stack_trace(self, client):
        r = client.post(
            "/users/",
            data=b"}{not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (400, 422)
        assert "Traceback" not in r.text
        assert "File " not in r.text
        assert "line " not in r.text.lower() or "detail" in r.json()

    def test_404_no_stack_trace(self, client, admin_headers):
        r = client.get("/users/definitely-nonexistent-99999", headers=admin_headers)
        assert r.status_code == 404
        assert "Traceback" not in r.text

    def test_401_no_stack_trace(self, client):
        r = client.get("/users/me", headers={"Authorization": "Bearer bad.token"})
        assert r.status_code == 401
        assert "Traceback" not in r.text

    def test_403_no_stack_trace(self, client, user_factory, regular_headers):
        other, _ = user_factory()
        r = client.delete(f"/users/{other.id}", headers=regular_headers)
        assert r.status_code == 403
        assert "Traceback" not in r.text


class TestTokenNotExposed:
    def test_tokens_not_in_list_response(self, client, regular_headers):
        r = client.get("/users/", headers=regular_headers)
        for user in r.json().get("items", []):
            assert "token" not in user
            assert "secret" not in user

    def test_tokens_not_in_user_detail(self, client, regular_user, regular_headers):
        r = client.get(f"/users/{regular_user.id}", headers=regular_headers)
        body = r.json()
        assert "token" not in body
        assert "secret" not in body
