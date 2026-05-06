"""Unit tests for app.auth — password hashing + JWT."""
from __future__ import annotations

import time
import pytest
import jwt as pyjwt

from app.auth import (
    hash_password,
    verify_password,
    create_token,
    decode_token,
    decode_token_unsafe,
    JWT_SECRET,
    JWT_ALG,
    JWT_TTL_SECONDS,
)


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------

class TestHashPassword:
    def test_hash_is_bcrypt(self):
        h = hash_password("secure_pass")
        assert h.startswith("$2b$")

    def test_hash_not_plain(self):
        h = hash_password("mypassword")
        assert h != "mypassword"

    def test_unique_salts(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # different salts

    def test_empty_password_raises(self):
        with pytest.raises(ValueError, match="empty"):
            hash_password("")


class TestVerifyPassword:
    def test_correct_password(self):
        h = hash_password("correct_horse")
        assert verify_password("correct_horse", h) is True

    def test_wrong_password(self):
        h = hash_password("correct_horse")
        assert verify_password("wrong_horse", h) is False

    def test_empty_plain_returns_false(self):
        h = hash_password("valid_password")
        assert verify_password("", h) is False

    def test_invalid_hash_returns_false(self):
        assert verify_password("anything", "not_a_hash") is False

    def test_none_inputs_raise_or_return_false(self):
        """verify_password does not guard None inputs — documents the gap."""
        # The function calls plain.encode() without checking for None,
        # which raises AttributeError. This is a known defensive-coding gap.
        with pytest.raises((AttributeError, TypeError)):
            verify_password(None, "something")  # type: ignore


# ---------------------------------------------------------------------------
# create_token / decode_token
# ---------------------------------------------------------------------------

class TestCreateToken:
    def test_returns_string(self):
        token = create_token(1, "user")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_payload_fields(self):
        token = create_token(42, "admin")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert "iat" in payload
        assert "exp" in payload

    def test_expiry_window(self):
        now = int(time.time())
        token = create_token(1, "user")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        assert payload["exp"] - payload["iat"] == JWT_TTL_SECONDS
        assert payload["iat"] >= now - 2  # allow 2s clock skew

    def test_default_role_is_user(self):
        token = create_token(1)
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        assert payload["role"] == "user"


class TestDecodeToken:
    def test_roundtrip(self):
        token = create_token(7, "user")
        payload = decode_token(token)
        assert payload["sub"] == "7"

    def test_invalid_token_raises(self):
        with pytest.raises(Exception):
            decode_token("not.a.token")

    def test_wrong_secret_raises(self):
        token = pyjwt.encode({"sub": "1", "exp": int(time.time()) + 3600}, "wrong-secret", algorithm="HS256")
        with pytest.raises(Exception):
            decode_token(token)

    def test_expired_token_raises(self):
        expired_payload = {
            "sub": "1",
            "role": "user",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
        token = pyjwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALG)
        with pytest.raises(Exception):
            decode_token(token)


# ---------------------------------------------------------------------------
# decode_token_unsafe — security: should NOT be used in production
# ---------------------------------------------------------------------------

class TestDecodeTokenUnsafe:
    def test_accepts_unsigned_token(self):
        """Demonstrates the unsafe function accepts unverified tokens — this is a security flaw."""
        unsigned_payload = {"sub": "99", "role": "admin"}
        # Create a token with no signature verification option
        unsigned_token = pyjwt.encode(unsigned_payload, "", algorithm="HS256")
        # decode_token_unsafe skips signature verification
        result = decode_token_unsafe(unsigned_token)
        assert result["sub"] == "99"

    def test_accepts_tampered_claims(self):
        """Any claims can be accepted — demonstrates the security risk."""
        tampered = pyjwt.encode({"sub": "1", "role": "superadmin"}, "any-key", algorithm="HS256")
        result = decode_token_unsafe(tampered)
        assert result["role"] == "superadmin"
