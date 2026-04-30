import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.auth import (
    create_token,
    verify_token,
    login,
    LoginRequest,
    SECRET_KEY,
    ALGORITHM,
    fake_users_db,
)


# ---------------------------------------------------------------------------
# create_token
# ---------------------------------------------------------------------------

class TestCreateToken:
    def test_returns_string(self):
        token = create_token(1, "user")
        assert isinstance(token, str)

    def test_payload_contains_sub_and_role(self):
        token = create_token(42, "admin")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"

    def test_token_expires_in_one_hour(self):
        before = datetime.utcnow()
        token = create_token(1, "user")
        after = datetime.utcnow()
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.utcfromtimestamp(payload["exp"])
        assert before + timedelta(minutes=59) < exp < after + timedelta(hours=1, seconds=5)

    def test_different_users_get_different_tokens(self):
        t1 = create_token(1, "user")
        t2 = create_token(2, "admin")
        assert t1 != t2

    def test_zero_user_id(self):
        token = create_token(0, "user")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "0"

    def test_large_user_id(self):
        token = create_token(9999999, "user")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "9999999"

    @pytest.mark.parametrize("role", ["user", "admin", "moderator", ""])
    def test_various_roles(self, role):
        token = create_token(1, role)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["role"] == role


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------

class TestVerifyToken:
    def _make_credentials(self, token: str) -> HTTPAuthorizationCredentials:
        creds = MagicMock(spec=HTTPAuthorizationCredentials)
        creds.credentials = token
        return creds

    def test_valid_token_returns_payload(self):
        token = create_token(1, "user")
        creds = self._make_credentials(token)
        payload = verify_token(creds)
        assert payload["sub"] == "1"
        assert payload["role"] == "user"

    def test_invalid_token_raises_401(self):
        creds = self._make_credentials("this.is.not.a.jwt")
        with pytest.raises(HTTPException) as exc:
            verify_token(creds)
        assert exc.value.status_code == 401
        assert "Invalid token" in exc.value.detail

    def test_expired_token_raises_401(self):
        payload = {"sub": "1", "role": "user", "exp": datetime.utcnow() - timedelta(seconds=1)}
        expired = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        creds = self._make_credentials(expired)
        with pytest.raises(HTTPException) as exc:
            verify_token(creds)
        assert exc.value.status_code == 401

    def test_tampered_signature_raises_401(self):
        token = create_token(1, "user")
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".invalidsignature"
        creds = self._make_credentials(tampered)
        with pytest.raises(HTTPException) as exc:
            verify_token(creds)
        assert exc.value.status_code == 401

    def test_alg_none_raises_401(self):
        import base64, json as _json
        header = base64.urlsafe_b64encode(_json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        body = base64.urlsafe_b64encode(_json.dumps({"sub": "1", "role": "admin"}).encode()).decode().rstrip("=")
        none_token = f"{header}.{body}."
        creds = self._make_credentials(none_token)
        with pytest.raises(HTTPException) as exc:
            verify_token(creds)
        assert exc.value.status_code == 401

    def test_empty_string_raises_401(self):
        creds = self._make_credentials("")
        with pytest.raises(HTTPException) as exc:
            verify_token(creds)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# login endpoint
# ---------------------------------------------------------------------------

class TestLogin:
    def test_valid_user_credentials_returns_token_and_id(self):
        req = LoginRequest(email="user@test.com", password="TestPass1!")
        result = login(req)
        assert "token" in result
        assert isinstance(result["token"], str)
        assert result["user_id"] == 1

    def test_valid_admin_credentials_returns_admin_token(self):
        req = LoginRequest(email="admin@test.com", password="AdminPass1!")
        result = login(req)
        payload = jwt.decode(result["token"], SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["role"] == "admin"

    def test_wrong_password_raises_401(self):
        req = LoginRequest(email="user@test.com", password="WrongPass!")
        with pytest.raises(HTTPException) as exc:
            login(req)
        assert exc.value.status_code == 401
        assert "Invalid credentials" in exc.value.detail

    def test_unknown_email_raises_401(self):
        req = LoginRequest(email="ghost@test.com", password="TestPass1!")
        with pytest.raises(HTTPException) as exc:
            login(req)
        assert exc.value.status_code == 401

    def test_empty_email_raises_401(self):
        req = LoginRequest(email="", password="TestPass1!")
        with pytest.raises(HTTPException) as exc:
            login(req)
        assert exc.value.status_code == 401

    def test_empty_password_raises_401(self):
        req = LoginRequest(email="user@test.com", password="")
        with pytest.raises(HTTPException) as exc:
            login(req)
        assert exc.value.status_code == 401

    def test_sql_injection_in_email_raises_401(self):
        req = LoginRequest(email="' OR '1'='1", password="anything")
        with pytest.raises(HTTPException) as exc:
            login(req)
        assert exc.value.status_code == 401

    @pytest.mark.parametrize("email,password", [
        ("user@test.com", "TestPass1!"),
        ("admin@test.com", "AdminPass1!"),
    ])
    def test_valid_credentials_parametrized(self, email, password):
        req = LoginRequest(email=email, password=password)
        result = login(req)
        assert "token" in result

    def test_login_is_idempotent(self):
        req = LoginRequest(email="user@test.com", password="TestPass1!")
        r1 = login(req)
        r2 = login(req)
        p1 = jwt.decode(r1["token"], SECRET_KEY, algorithms=[ALGORITHM])
        p2 = jwt.decode(r2["token"], SECRET_KEY, algorithms=[ALGORITHM])
        assert p1["sub"] == p2["sub"]
        assert p1["role"] == p2["role"]

    def test_response_does_not_expose_password(self):
        req = LoginRequest(email="user@test.com", password="TestPass1!")
        result = login(req)
        result_str = str(result)
        assert "TestPass1!" not in result_str
        assert "hashed_password" not in result_str


# ---------------------------------------------------------------------------
# get_me endpoint
# ---------------------------------------------------------------------------

class TestGetMe:
    def test_returns_user_id_and_role(self):
        from src.auth import get_me
        token_data = {"sub": "1", "role": "user"}
        result = get_me(token_data)
        assert result["user_id"] == "1"
        assert result["role"] == "user"

    def test_admin_role_reflected(self):
        from src.auth import get_me
        token_data = {"sub": "2", "role": "admin"}
        result = get_me(token_data)
        assert result["role"] == "admin"
