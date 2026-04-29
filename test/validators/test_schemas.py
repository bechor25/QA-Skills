"""Validate shared schemas and message catalog consistency."""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SHARED = os.path.join(ROOT, "skills", "_shared")


def test_schemas_valid_json():
    schemas_dir = os.path.join(SHARED, "schemas")
    for fname in os.listdir(schemas_dir):
        if fname.endswith(".schema.json"):
            with open(os.path.join(schemas_dir, fname)) as f:
                data = json.load(f)
            assert "$schema" in data, f"{fname} missing $schema"
            assert "type" in data or "properties" in data, f"{fname} missing type or properties"


def test_messages_keys_match():
    he_path = os.path.join(SHARED, "messages", "he.json")
    en_path = os.path.join(SHARED, "messages", "en.json")
    with open(he_path) as f:
        he = json.load(f)
    with open(en_path) as f:
        en = json.load(f)
    missing_in_en = set(he.keys()) - set(en.keys())
    missing_in_he = set(en.keys()) - set(he.keys())
    assert not missing_in_en, f"Keys in he.json but not en.json: {missing_in_en}"
    assert not missing_in_he, f"Keys in en.json but not he.json: {missing_in_he}"


def test_validate_helper_works():
    sys.path.insert(0, SHARED)
    from validate import validate_or_warn, get_message
    ok, errors = validate_or_warn({"run_id": "x", "project_root": "/tmp",
                                   "language": "python", "user_locale": "en",
                                   "categories_enabled": ["unit"]}, "run_context")
    assert ok, f"Valid RunContext failed: {errors}"
    msg = get_message("scan_start", "en", path="/tmp/proj")
    assert "/tmp/proj" in msg


if __name__ == "__main__":
    test_schemas_valid_json()
    test_messages_keys_match()
    test_validate_helper_works()
    print("✅ schema + message tests passed")
