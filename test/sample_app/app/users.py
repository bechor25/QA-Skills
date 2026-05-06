"""In-memory user store. Real apps swap this for SQL/NoSQL — interface stable."""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from app.auth import hash_password, verify_password


@dataclass
class User:
    id: int
    email: str
    name: str
    password_hash: str
    role: str = "user"

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name, "role": self.role}


class UserStore:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._next_id = 1
        self._lock = Lock()

    def create(self, email: str, name: str, password: str, role: str = "user") -> User:
        with self._lock:
            if any(u.email == email for u in self._users.values()):
                raise ValueError("email already registered")
            user = User(
                id=self._next_id,
                email=email,
                name=name,
                password_hash=hash_password(password),
                role=role,
            )
            self._users[user.id] = user
            self._next_id += 1
            return user

    def get(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    def list(self) -> list[User]:
        return list(self._users.values())

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.get_by_email(email)
        if user and verify_password(password, user.password_hash):
            return user
        return None

    def delete(self, user_id: int) -> bool:
        with self._lock:
            return self._users.pop(user_id, None) is not None


store = UserStore()


def seed_demo_users() -> None:
    """Idempotent demo seed — safe to call on app startup."""
    if store.get_by_email("admin@example.com"):
        return
    store.create("admin@example.com", "Admin", "admin1234", role="admin")
    store.create("alice@example.com", "Alice", "alice1234")
