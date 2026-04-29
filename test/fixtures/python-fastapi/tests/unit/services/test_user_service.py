import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from app.services import user_service
from app.models.user import User


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def sample_user():
    u = MagicMock()
    u.id = "user-uuid-123"
    u.email = "alice@example.com"
    u.name = "Alice"
    u.role = "user"
    u.password_hash = user_service.hash_password("Secret123!")
    return u


class TestHashPassword:
    def test_returns_string(self):
        assert isinstance(user_service.hash_password("password"), str)

    def test_different_hashes_for_same_password(self):
        h1 = user_service.hash_password("password")
        h2 = user_service.hash_password("password")
        assert h1 != h2

    def test_empty_string_hashes_without_crash(self):
        result = user_service.hash_password("")
        assert isinstance(result, str)
        assert len(result) > 0


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = user_service.hash_password("MyPass1!")
        assert user_service.verify_password("MyPass1!", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = user_service.hash_password("MyPass1!")
        assert user_service.verify_password("WrongPass!", hashed) is False

    def test_empty_password_returns_false(self):
        hashed = user_service.hash_password("MyPass1!")
        assert user_service.verify_password("", hashed) is False

    def test_case_sensitive(self):
        hashed = user_service.hash_password("Password")
        assert user_service.verify_password("password", hashed) is False

    def test_unicode_password(self):
        hashed = user_service.hash_password("日本語パスワード")
        assert user_service.verify_password("日本語パスワード", hashed) is True
        assert user_service.verify_password("日本語", hashed) is False


class TestCreateAccessToken:
    def test_returns_string(self):
        assert isinstance(user_service.create_access_token("user-1", "user"), str)

    def test_token_has_three_jwt_parts(self):
        token = user_service.create_access_token("user-1", "user")
        assert len(token.split(".")) == 3

    def test_different_users_get_different_tokens(self):
        t1 = user_service.create_access_token("user-1", "user")
        t2 = user_service.create_access_token("user-2", "user")
        assert t1 != t2

    def test_admin_role_embedded_in_token(self):
        t1 = user_service.create_access_token("user-1", "user")
        t2 = user_service.create_access_token("user-1", "admin")
        assert t1 != t2


class TestVerifyToken:
    def test_valid_token_returns_payload(self):
        token = user_service.create_access_token("user-1", "user")
        payload = user_service.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["role"] == "user"

    def test_invalid_token_returns_none(self):
        assert user_service.verify_token("invalid.token.here") is None

    def test_empty_string_returns_none(self):
        assert user_service.verify_token("") is None

    def test_tampered_signature_returns_none(self):
        token = user_service.create_access_token("user-1", "user")
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalidsignature"
        assert user_service.verify_token(tampered) is None

    def test_expired_token_returns_none(self):
        from jose import jwt
        expired_payload = {
            "sub": "user-1",
            "role": "user",
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload,
            user_service.SECRET_KEY,
            algorithm=user_service.ALGORITHM,
        )
        assert user_service.verify_token(expired_token) is None

    def test_wrong_secret_returns_none(self):
        from jose import jwt
        payload = {"sub": "user-1", "role": "user", "exp": datetime.utcnow() + timedelta(hours=1)}
        bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        assert user_service.verify_token(bad_token) is None


class TestAuthenticateUser:
    def test_valid_credentials_returns_user(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        result = user_service.authenticate_user(mock_db, "alice@example.com", "Secret123!")
        assert result == sample_user

    def test_wrong_password_returns_none(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        result = user_service.authenticate_user(mock_db, "alice@example.com", "WrongPass!")
        assert result is None

    def test_nonexistent_user_returns_none(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = user_service.authenticate_user(mock_db, "nobody@example.com", "Pass!")
        assert result is None

    def test_empty_email_raises_value_error(self, mock_db):
        with pytest.raises(ValueError, match="Email and password required"):
            user_service.authenticate_user(mock_db, "", "Pass!")

    def test_empty_password_raises_value_error(self, mock_db):
        with pytest.raises(ValueError, match="Email and password required"):
            user_service.authenticate_user(mock_db, "user@test.com", "")

    def test_none_email_raises_value_error(self, mock_db):
        with pytest.raises(ValueError):
            user_service.authenticate_user(mock_db, None, "Pass!")

    def test_none_password_raises_value_error(self, mock_db):
        with pytest.raises(ValueError):
            user_service.authenticate_user(mock_db, "user@test.com", None)

    def test_db_queried_with_user_model(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        user_service.authenticate_user(mock_db, "alice@example.com", "Secret123!")
        mock_db.query.assert_called_with(User)


class TestGetUserById:
    def test_existing_user_returned(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        result = user_service.get_user_by_id(mock_db, "user-uuid-123")
        assert result == sample_user

    def test_missing_user_returns_none(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = user_service.get_user_by_id(mock_db, "nonexistent-id")
        assert result is None

    def test_db_queried_with_user_model(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        user_service.get_user_by_id(mock_db, "user-uuid-123")
        mock_db.query.assert_called_with(User)


class TestGetAllUsers:
    def test_returns_users_and_total(self, mock_db, sample_user):
        mock_db.query.return_value.count.return_value = 5
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = [sample_user]
        users, total = user_service.get_all_users(mock_db, page=1, limit=10)
        assert total == 5
        assert users == [sample_user]

    def test_pagination_offset_calculation(self, mock_db):
        mock_db.query.return_value.count.return_value = 20
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
        user_service.get_all_users(mock_db, page=3, limit=5)
        mock_db.query.return_value.offset.assert_called_with(10)  # (3-1)*5

    def test_default_pagination(self, mock_db):
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
        user_service.get_all_users(mock_db)
        mock_db.query.return_value.offset.assert_called_with(0)
        mock_db.query.return_value.offset.return_value.limit.assert_called_with(10)

    def test_empty_db_returns_zero_total(self, mock_db):
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
        users, total = user_service.get_all_users(mock_db)
        assert total == 0
        assert users == []


class TestCreateUser:
    def test_creates_user_and_calls_db(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = user_service.create_user(mock_db, "new@example.com", "Pass123!", "New User")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert result.email == "new@example.com"
        assert result.name == "New User"

    def test_password_not_stored_raw(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = user_service.create_user(mock_db, "new@example.com", "PlainPass!", "New")
        assert result.password_hash != "PlainPass!"

    def test_duplicate_email_raises_value_error(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        with pytest.raises(ValueError, match="Email already registered"):
            user_service.create_user(mock_db, "alice@example.com", "Pass123!", "Alice")

    def test_duplicate_email_does_not_add_to_db(self, mock_db, sample_user):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user
        try:
            user_service.create_user(mock_db, "alice@example.com", "Pass123!", "Alice")
        except ValueError:
            pass
        mock_db.add.assert_not_called()


class TestUpdateUser:
    def test_updates_name_successfully(self, mock_db, sample_user):
        with patch.object(user_service, "get_user_by_id", return_value=sample_user):
            result = user_service.update_user(mock_db, "user-uuid-123", "New Name")
        assert result == sample_user
        assert sample_user.name == "New Name"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_nonexistent_user_returns_none(self, mock_db):
        with patch.object(user_service, "get_user_by_id", return_value=None):
            result = user_service.update_user(mock_db, "nonexistent", "Name")
        assert result is None
        mock_db.commit.assert_not_called()

    def test_none_name_does_not_change_name(self, mock_db, sample_user):
        sample_user.name = "Original"
        with patch.object(user_service, "get_user_by_id", return_value=sample_user):
            user_service.update_user(mock_db, "user-uuid-123", None)
        assert sample_user.name == "Original"

    def test_empty_name_does_not_change_name(self, mock_db, sample_user):
        sample_user.name = "Original"
        with patch.object(user_service, "get_user_by_id", return_value=sample_user):
            user_service.update_user(mock_db, "user-uuid-123", "")
        assert sample_user.name == "Original"

    @pytest.mark.parametrize("name", ["日本語名前", "<script>alert(1)</script>", "x" * 10001])
    def test_unusual_name_values_accepted(self, mock_db, sample_user, name):
        with patch.object(user_service, "get_user_by_id", return_value=sample_user):
            result = user_service.update_user(mock_db, "user-uuid-123", name)
        assert result is not None


class TestDeleteUser:
    def test_deletes_existing_user(self, mock_db, sample_user):
        with patch.object(user_service, "get_user_by_id", return_value=sample_user):
            result = user_service.delete_user(mock_db, "user-uuid-123")
        assert result is True
        mock_db.delete.assert_called_once_with(sample_user)
        mock_db.commit.assert_called_once()

    def test_nonexistent_user_returns_false(self, mock_db):
        with patch.object(user_service, "get_user_by_id", return_value=None):
            result = user_service.delete_user(mock_db, "nonexistent")
        assert result is False
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()
