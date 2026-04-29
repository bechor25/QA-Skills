"""Validate contract-with-openapi fixture has valid OpenAPI spec."""
import os, re

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "contract-with-openapi")


def test_openapi_exists():
    assert os.path.isfile(os.path.join(FIXTURE, "openapi.yaml")), "openapi.yaml missing"


def test_openapi_has_required_routes():
    content = open(os.path.join(FIXTURE, "openapi.yaml")).read()
    assert "/auth/login" in content
    assert "/users" in content
    assert "token" in content
    assert "required:" in content


def test_openapi_has_response_schemas():
    content = open(os.path.join(FIXTURE, "openapi.yaml")).read()
    assert "properties:" in content
    assert "type: object" in content
    assert '"200"' in content or "'200'" in content or "\n        \"200\"" in content or "200:" in content


def test_app_has_matching_routes():
    app_path = os.path.join(FIXTURE, "src", "app.py")
    assert os.path.isfile(app_path)
    content = open(app_path).read()
    assert "/auth/login" in content
    assert "/users" in content


if __name__ == "__main__":
    test_openapi_exists()
    test_openapi_has_required_routes()
    test_openapi_has_response_schemas()
    test_app_has_matching_routes()
    print("✅ contract fixture tests passed")
