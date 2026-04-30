import pytest
import concurrent.futures
from fastapi.testclient import TestClient

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from main import app
from src.users import users_store


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def user_token(client):
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "TestPass1!"})
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/auth/login", json={"email": "admin@test.com", "password": "AdminPass1!"})
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(autouse=True)
def reset_users_store():
    original = {k: v.copy() for k, v in users_store.items()}
    yield
    users_store.clear()
    users_store.update(original)


# ---------------------------------------------------------------------------
# GET /users/
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_authenticated_returns_200(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        assert r.status_code == 200

    def test_no_token_returns_401_or_403(self, client):
        r = client.get("/users/")
        assert r.status_code in (401, 403)

    def test_response_has_items_and_total(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)

    def test_total_matches_items_count(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        body = r.json()
        assert body["total"] == len(body["items"])

    def test_items_not_null(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        for item in r.json()["items"]:
            assert item is not None

    def test_passwords_not_exposed(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        for item in r.json()["items"]:
            assert "password" not in item
            assert "hashed_password" not in item

    def test_get_is_readonly(self, client, user_headers):
        before = client.get("/users/", headers=user_headers).json()
        client.get("/users/", headers=user_headers)
        after = client.get("/users/", headers=user_headers).json()
        assert before["total"] == after["total"]

    def test_content_type_is_json(self, client, user_headers):
        r = client.get("/users/", headers=user_headers)
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_existing_user_returns_200(self, client, user_headers):
        r = client.get("/users/1", headers=user_headers)
        assert r.status_code == 200
        assert r.json()["id"] == 1

    def test_nonexistent_returns_404(self, client, user_headers):
        r = client.get("/users/99999", headers=user_headers)
        assert r.status_code == 404

    def test_no_token_returns_401_or_403(self, client):
        r = client.get("/users/1")
        assert r.status_code in (401, 403)

    def test_string_id_returns_422(self, client, user_headers):
        r = client.get("/users/abc", headers=user_headers)
        assert r.status_code in (400, 404, 422)

    def test_negative_id_returns_404(self, client, user_headers):
        r = client.get("/users/-1", headers=user_headers)
        assert r.status_code == 404

    def test_response_does_not_expose_password(self, client, user_headers):
        r = client.get("/users/1", headers=user_headers)
        assert "password" not in r.json()


# ---------------------------------------------------------------------------
# PUT /users/{user_id}
# ---------------------------------------------------------------------------

class TestUpdateUser:
    def test_user_can_update_own_name(self, client, user_headers):
        r = client.put("/users/1", json={"name": "Alice New"}, headers=user_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "Alice New"

    def test_admin_can_update_any_user(self, client, admin_headers):
        r = client.put("/users/1", json={"name": "AdminEdited"}, headers=admin_headers)
        assert r.status_code == 200

    def test_user_cannot_update_other_user(self, client, user_headers):
        r = client.put("/users/2", json={"name": "Hacked"}, headers=user_headers)
        assert r.status_code == 403

    def test_update_nonexistent_returns_404(self, client, admin_headers):
        r = client.put("/users/9999", json={"name": "Ghost"}, headers=admin_headers)
        assert r.status_code == 404

    def test_no_token_returns_401_or_403(self, client):
        r = client.put("/users/1", json={"name": "Anon"})
        assert r.status_code in (401, 403)

    def test_put_is_idempotent(self, client, user_headers):
        r1 = client.put("/users/1", json={"name": "Alice"}, headers=user_headers)
        r2 = client.put("/users/1", json={"name": "Alice"}, headers=user_headers)
        assert r1.json() == r2.json()

    def test_concurrent_updates_no_500(self, client, user_headers):
        def update():
            return client.put("/users/1", json={"name": "Alice"}, headers=user_headers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(update) for _ in range(5)]
            results = [f.result() for f in futures]

        statuses = [r.status_code for r in results]
        assert 500 not in statuses


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}
# ---------------------------------------------------------------------------

class TestDeleteUser:
    def test_admin_can_delete_user(self, client, admin_headers):
        r = client.delete("/users/1", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["deleted"] == 1

    def test_regular_user_cannot_delete(self, client, user_headers):
        r = client.delete("/users/2", headers=user_headers)
        assert r.status_code == 403

    def test_no_token_returns_401_or_403(self, client):
        r = client.delete("/users/1")
        assert r.status_code in (401, 403)

    def test_delete_nonexistent_returns_404(self, client, admin_headers):
        r = client.delete("/users/9999", headers=admin_headers)
        assert r.status_code == 404

    def test_deleted_user_no_longer_accessible(self, client, admin_headers, user_headers):
        client.delete("/users/1", headers=admin_headers)
        r = client.get("/users/1", headers=user_headers)
        assert r.status_code == 404

    def test_response_content_type_is_json(self, client, admin_headers):
        r = client.delete("/users/2", headers=admin_headers)
        assert "application/json" in r.headers.get("content-type", "")
