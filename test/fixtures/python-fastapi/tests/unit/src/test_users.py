import pytest
from fastapi import HTTPException

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.users import (
    get_user_or_404,
    list_users,
    get_user,
    update_user,
    delete_user,
    UserUpdate,
    users_store,
)


@pytest.fixture(autouse=True)
def reset_users_store():
    original = {k: v.copy() for k, v in users_store.items()}
    yield
    users_store.clear()
    users_store.update(original)


USER_TOKEN = {"sub": "1", "role": "user"}
ADMIN_TOKEN = {"sub": "2", "role": "admin"}


# ---------------------------------------------------------------------------
# get_user_or_404
# ---------------------------------------------------------------------------

class TestGetUserOr404:
    def test_existing_user_returns_user(self):
        user = get_user_or_404(1)
        assert user["id"] == 1
        assert user["email"] == "user@test.com"

    def test_missing_user_raises_404(self):
        with pytest.raises(HTTPException) as exc:
            get_user_or_404(99999)
        assert exc.value.status_code == 404
        assert "User not found" in exc.value.detail

    def test_zero_id_raises_404(self):
        with pytest.raises(HTTPException) as exc:
            get_user_or_404(0)
        assert exc.value.status_code == 404

    def test_negative_id_raises_404(self):
        with pytest.raises(HTTPException) as exc:
            get_user_or_404(-1)
        assert exc.value.status_code == 404

    @pytest.mark.parametrize("user_id", [1, 2])
    def test_known_ids_return_users(self, user_id):
        user = get_user_or_404(user_id)
        assert user["id"] == user_id


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_returns_items_and_total(self):
        result = list_users(token_data=USER_TOKEN)
        assert "items" in result
        assert "total" in result
        assert isinstance(result["items"], list)

    def test_total_matches_items_count(self):
        result = list_users(token_data=USER_TOKEN)
        assert result["total"] == len(result["items"])

    def test_items_contain_expected_fields(self):
        result = list_users(token_data=USER_TOKEN)
        for item in result["items"]:
            assert "id" in item
            assert "email" in item
            assert "name" in item

    def test_passwords_not_in_response(self):
        result = list_users(token_data=USER_TOKEN)
        for item in result["items"]:
            assert "password" not in item
            assert "hashed_password" not in item


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_returns_correct_user(self):
        result = get_user(1, token_data=USER_TOKEN)
        assert result["id"] == 1

    def test_nonexistent_user_raises_404(self):
        with pytest.raises(HTTPException) as exc:
            get_user(9999, token_data=USER_TOKEN)
        assert exc.value.status_code == 404

    def test_get_does_not_mutate_store(self):
        before = {k: v.copy() for k, v in users_store.items()}
        get_user(1, token_data=USER_TOKEN)
        assert users_store == before


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_user_can_update_own_name(self):
        update = UserUpdate(name="Alice Updated")
        result = update_user(1, update, token_data=USER_TOKEN)
        assert result["name"] == "Alice Updated"

    def test_user_can_update_own_email(self):
        update = UserUpdate(email="newalice@test.com")
        result = update_user(1, update, token_data=USER_TOKEN)
        assert result["email"] == "newalice@test.com"

    def test_admin_can_update_any_user(self):
        update = UserUpdate(name="AdminEdited")
        result = update_user(1, update, token_data=ADMIN_TOKEN)
        assert result["name"] == "AdminEdited"

    def test_user_cannot_update_other_user(self):
        update = UserUpdate(name="Hacked")
        with pytest.raises(HTTPException) as exc:
            update_user(2, update, token_data=USER_TOKEN)
        assert exc.value.status_code == 403
        assert "Forbidden" in exc.value.detail

    def test_nonexistent_user_raises_404(self):
        update = UserUpdate(name="Ghost")
        with pytest.raises(HTTPException) as exc:
            update_user(9999, update, token_data=ADMIN_TOKEN)
        assert exc.value.status_code == 404

    def test_empty_update_leaves_name_unchanged(self):
        original_name = users_store[1]["name"]
        update = UserUpdate()
        result = update_user(1, update, token_data=USER_TOKEN)
        assert result["name"] == original_name

    def test_update_idempotent_on_same_value(self):
        update = UserUpdate(name="Alice")
        r1 = update_user(1, update, token_data=USER_TOKEN)
        r2 = update_user(1, update, token_data=USER_TOKEN)
        assert r1["name"] == r2["name"]

    def test_unicode_name_accepted(self):
        update = UserUpdate(name="אליס בן-דוד")
        result = update_user(1, update, token_data=USER_TOKEN)
        assert result["name"] == "אליס בן-דוד"

    def test_very_long_name(self):
        long_name = "A" * 10001
        update = UserUpdate(name=long_name)
        result = update_user(1, update, token_data=USER_TOKEN)
        assert result["name"] == long_name


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_admin_can_delete_user(self):
        result = delete_user(1, token_data=ADMIN_TOKEN)
        assert result["deleted"] == 1
        assert 1 not in users_store

    def test_regular_user_cannot_delete(self):
        with pytest.raises(HTTPException) as exc:
            delete_user(1, token_data=USER_TOKEN)
        assert exc.value.status_code == 403
        assert "Admin only" in exc.value.detail

    def test_delete_nonexistent_raises_404(self):
        with pytest.raises(HTTPException) as exc:
            delete_user(9999, token_data=ADMIN_TOKEN)
        assert exc.value.status_code == 404

    def test_deleted_user_no_longer_retrievable(self):
        delete_user(1, token_data=ADMIN_TOKEN)
        with pytest.raises(HTTPException) as exc:
            get_user_or_404(1)
        assert exc.value.status_code == 404

    def test_delete_returns_deleted_id(self):
        result = delete_user(2, token_data=ADMIN_TOKEN)
        assert result == {"deleted": 2}
