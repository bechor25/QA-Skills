"""Auth helpers — password hashing + JWT.

Note: contains a couple of intentionally weak patterns for the security-test
skill to flag (alg=none acceptance in `decode_token_unsafe`, hardcoded secret
fallback). These are NOT used by the production endpoints — they exist as
realistic targets the security skill should detect.
"""
from __future__ import annotations

import os
import time
from typing import Any

import bcrypt
import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 3600


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def create_token(user_id: int, role: str = "user") -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def decode_token_unsafe(token: str) -> dict[str, Any]:
    """LEGACY — accepts unsigned tokens. Do not use; flagged for security review."""
    return jwt.decode(token, options={"verify_signature": False})
