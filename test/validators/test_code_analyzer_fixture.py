"""Validate that the python-fastapi fixture has detectable structure for code-analyzer."""
import os

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "python-fastapi")


def test_fixture_exists():
    assert os.path.isdir(FIXTURE), "python-fastapi fixture missing"
    assert os.path.isfile(os.path.join(FIXTURE, "requirements.txt"))
    assert os.path.isfile(os.path.join(FIXTURE, "src", "auth.py"))
    assert os.path.isfile(os.path.join(FIXTURE, "src", "users.py"))


def test_fixture_has_detectable_patterns():
    auth_content = open(os.path.join(FIXTURE, "src", "auth.py")).read()
    # Must have routes, auth, db-like patterns
    assert "@router.post" in auth_content or "@app.post" in auth_content
    assert "jwt" in auth_content.lower() or "bcrypt" in auth_content.lower()
    assert "def " in auth_content

    users_content = open(os.path.join(FIXTURE, "src", "users.py")).read()
    assert "@router.get" in users_content or "router.get" in users_content
    assert "def " in users_content


def test_typescript_fixture_exists():
    ts_fixture = os.path.join(os.path.dirname(__file__), "..", "fixtures", "typescript-express")
    assert os.path.isdir(ts_fixture)
    assert os.path.isfile(os.path.join(ts_fixture, "package.json"))
    pkg = open(os.path.join(ts_fixture, "package.json")).read()
    assert "jest" in pkg


if __name__ == "__main__":
    test_fixture_exists()
    test_fixture_has_detectable_patterns()
    test_typescript_fixture_exists()
    print("✅ code-analyzer fixture tests passed")
