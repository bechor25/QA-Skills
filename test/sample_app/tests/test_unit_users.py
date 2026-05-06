"""Unit tests for app.users — UserStore in-memory store."""
from __future__ import annotations

import pytest

from app.users import UserStore, User


@pytest.fixture()
def store():
    """Fresh isolated store for each test."""
    return UserStore()


class TestUserStoreCreate:
    def test_creates_user(self, store):
        user = store.create("a@b.com", "Alice", "password1")
        assert isinstance(user, User)
        assert user.email == "a@b.com"
        assert user.name == "Alice"
        assert user.role == "user"
        assert user.id == 1

    def test_ids_increment(self, store):
        u1 = store.create("a@b.com", "Alice", "password1")
        u2 = store.create("b@b.com", "Bob", "password2")
        assert u2.id == u1.id + 1

    def test_duplicate_email_raises(self, store):
        store.create("a@b.com", "Alice", "password1")
        with pytest.raises(ValueError, match="already registered"):
            store.create("a@b.com", "Alice2", "password2")

    def test_admin_role(self, store):
        user = store.create("admin@b.com", "Admin", "password1", role="admin")
        assert user.role == "admin"

    def test_password_is_hashed(self, store):
        user = store.create("a@b.com", "Alice", "plain_password")
        assert user.password_hash != "plain_password"
        assert user.password_hash.startswith("$2b$")


class TestUserStoreGet:
    def test_get_existing(self, store):
        user = store.create("a@b.com", "Alice", "password1")
        fetched = store.get(user.id)
        assert fetched is not None
        assert fetched.id == user.id

    def test_get_nonexistent_returns_none(self, store):
        assert store.get(999) is None

    def test_get_by_email(self, store):
        store.create("a@b.com", "Alice", "password1")
        found = store.get_by_email("a@b.com")
        assert found is not None
        assert found.name == "Alice"

    def test_get_by_email_not_found(self, store):
        assert store.get_by_email("nobody@b.com") is None


class TestUserStoreList:
    def test_empty_store(self, store):
        assert store.list() == []

    def test_list_all(self, store):
        store.create("a@b.com", "A", "password1")
        store.create("b@b.com", "B", "password2")
        users = store.list()
        assert len(users) == 2

    def test_list_returns_user_objects(self, store):
        store.create("a@b.com", "A", "password1")
        users = store.list()
        assert all(isinstance(u, User) for u in users)


class TestUserStoreAuthenticate:
    def test_valid_credentials(self, store):
        store.create("a@b.com", "Alice", "correct_password")
        user = store.authenticate("a@b.com", "correct_password")
        assert user is not None
        assert user.email == "a@b.com"

    def test_wrong_password(self, store):
        store.create("a@b.com", "Alice", "correct_password")
        result = store.authenticate("a@b.com", "wrong_password")
        assert result is None

    def test_nonexistent_user(self, store):
        result = store.authenticate("ghost@b.com", "any")
        assert result is None

    def test_empty_password(self, store):
        store.create("a@b.com", "Alice", "correct_password")
        result = store.authenticate("a@b.com", "")
        assert result is None


class TestUserStoreDelete:
    def test_delete_existing(self, store):
        user = store.create("a@b.com", "A", "password1")
        result = store.delete(user.id)
        assert result is True
        assert store.get(user.id) is None

    def test_delete_nonexistent(self, store):
        assert store.delete(999) is False

    def test_delete_reduces_list(self, store):
        u1 = store.create("a@b.com", "A", "password1")
        store.create("b@b.com", "B", "password2")
        store.delete(u1.id)
        assert len(store.list()) == 1


class TestUserPublic:
    def test_public_does_not_expose_hash(self, store):
        user = store.create("a@b.com", "Alice", "password1")
        public = user.public()
        assert "password_hash" not in public
        assert set(public.keys()) == {"id", "email", "name", "role"}
