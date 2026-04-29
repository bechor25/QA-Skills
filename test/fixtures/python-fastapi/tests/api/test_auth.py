import pytest

EXPIRED_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1c2VyLTEiLCJyb2xlIjoidXNlciIsImV4cCI6MX0"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


class TestPostAuthLogin:
    def test_valid_credentials_return_token(self, client, user_factory):
        user, pwd = user_factory()
        r = client.post("/auth/login", json={"email": user.email, "password": pwd})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert isinstance(body["token"], str)
        assert len(body["token"].split(".")) == 3
        assert body.get("token_type") == "bearer"

    def test_wrong_password_returns_401(self, client, regular_user):
        r = client.post("/auth/login", json={"email": regular_user.email, "password": "WrongPass999!"})
        assert r.status_code == 401

    def test_nonexistent_email_returns_401(self, client):
        r = client.post("/auth/login", json={"email": "nobody_xyz@nowhere.com", "password": "Pass123!"})
        assert r.status_code == 401

    def test_missing_password_returns_422(self, client):
        r = client.post("/auth/login", json={"email": "user@example.com"})
        assert r.status_code == 422

    def test_missing_email_returns_422(self, client):
        r = client.post("/auth/login", json={"password": "Pass123!"})
        assert r.status_code == 422

    def test_invalid_email_format_returns_422(self, client):
        r = client.post("/auth/login", json={"email": "not-an-email", "password": "Pass123!"})
        assert r.status_code == 422

    def test_empty_body_returns_422(self, client):
        r = client.post("/auth/login", json={})
        assert r.status_code == 422

    def test_password_not_in_error_response(self, client):
        r = client.post("/auth/login", json={"email": "x@example.com", "password": "secret_value"})
        assert r.status_code in (400, 401, 422)
        assert "secret_value" not in r.text
        assert "hash" not in r.text.lower()

    def test_no_stack_trace_in_error(self, client):
        r = client.post(
            "/auth/login",
            data=b"}{invalid",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (400, 422)
        assert "Traceback" not in r.text
        assert "File " not in r.text

    def test_token_not_returned_for_wrong_credentials(self, client):
        r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
        assert r.status_code in (400, 401, 422)
        body = r.json()
        assert "token" not in body


class TestPostAuthLogout:
    def test_logout_returns_success(self, client):
        r = client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_logout_with_auth_header_returns_success(self, client, regular_headers):
        r = client.post("/auth/logout", headers=regular_headers)
        assert r.status_code == 200
