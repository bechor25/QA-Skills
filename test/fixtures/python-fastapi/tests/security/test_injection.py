import uuid
import pytest

SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "1' UNION SELECT null, null, null--",
    "' OR 1=1--",
    "admin'--",
    "1; SELECT sleep(5)--",
    "' AND 1=2 UNION SELECT username,password FROM users--",
]


class TestSQLInjectionLogin:
    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_email_cannot_authenticate(self, client, payload):
        r = client.post("/auth/login", json={"email": payload, "password": "pass"})
        assert r.status_code in (400, 401, 422), \
            f"SQL injection email returned unexpected {r.status_code}"
        assert "token" not in r.json()

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_password_cannot_authenticate(self, client, payload):
        r = client.post("/auth/login", json={"email": "user@test.com", "password": payload})
        assert r.status_code in (400, 401, 422)
        assert "token" not in r.json()

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_no_db_error_leaked_in_response(self, client, payload):
        r = client.post("/auth/login", json={"email": payload, "password": payload})
        text = r.text.lower()
        assert "syntax error" not in text
        assert "information_schema" not in text
        assert "sqlite" not in text
        assert r.status_code != 500, f"500 on injection payload — possible crash: {payload!r}"


class TestSQLInjectionUserCreation:
    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_name_field(self, client, payload):
        uid = uuid.uuid4().hex[:6]
        r = client.post("/users/", json={
            "email": f"injtest_{uid}@example.com",
            "password": "Pass123!",
            "name": payload,
        })
        assert r.status_code in (201, 400, 422)
        assert r.status_code != 500, f"500 on name injection payload: {payload!r}"
        if r.status_code == 201:
            assert "syntax error" not in r.text.lower()

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_user_id_path(self, client, admin_headers, payload):
        r = client.get(f"/users/{payload}", headers=admin_headers)
        assert r.status_code in (400, 404, 422)
        assert r.status_code != 500
        assert "syntax error" not in r.text.lower()
